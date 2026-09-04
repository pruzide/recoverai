from datetime import timedelta
from uuid import UUID

import structlog
from sqlalchemy import update
from sqlalchemy.exc import DBAPIError, OperationalError

from app.celery_app import celery_app
from app.db import get_session_factory
from app.domain.policy import evaluate_policy
from app.domain.recovery_engine import evaluate_recovery
from app.domain.recovery_state import InvalidStateTransition, validate_transition
from app.models import AuditEvent, OutboxEvent, RecoveryCase
from app.models.enums import (
    RecoveryActionStatus,
    RecoveryActionType,
    RecoveryCaseStatus,
)
from app.services.policy_service import (
    build_policy_input,
    get_or_create_default_policy,
    policy_limits_from,
)
from app.services.recovery_actions import (
    create_recovery_action_idempotent,
    recovery_action_idempotency_key,
)
from app.services.recovery_cases import (
    atomic_transition_recovery_case,
    utcnow,
)
from app.tasks.backoff import exponential_backoff_with_jitter


logger = structlog.get_logger()


def _insert_decision_audit(
    session,
    case: RecoveryCase,
    outbox_event_id: str,
    engine_action: RecoveryActionType,
    final_action: RecoveryActionType,
    policy_approved: bool,
    policy_reason: str,
    final_status: RecoveryCaseStatus,
) -> None:
    audit = AuditEvent(
        merchant_id=case.merchant_id,
        entity_type="recovery_case",
        entity_id=str(case.id),
        event_type="recovery_case.decision",
        actor="policy_worker",
        correlation_id=None,
        payload={
            "outbox_event_id": outbox_event_id,
            "engine_action": engine_action.value,
            "final_action": final_action.value,
            "policy_approved": policy_approved,
            "policy_reason": policy_reason,
            "final_status": final_status.value,
        },
    )

    session.add(audit)
    session.flush()


def _atomic_transition_with_next_action_at(
    session,
    case_id: UUID,
    expected_status: RecoveryCaseStatus,
    expected_version: int,
    new_status: RecoveryCaseStatus,
    next_action_at,
) -> int:
    validate_transition(expected_status, new_status)

    result = session.execute(
        update(RecoveryCase)
        .where(
            RecoveryCase.id == case_id,
            RecoveryCase.status == expected_status,
            RecoveryCase.version == expected_version,
        )
        .values(
            status=new_status,
            version=expected_version + 1,
            updated_at=utcnow(),
            next_action_at=next_action_at,
        )
    )

    return max(0, result.rowcount)


def _handle_recovery_case_eligible(session, outbox: OutboxEvent) -> dict:
    case_id_raw = outbox.payload.get("recovery_case_id")

    try:
        case_id = UUID(str(case_id_raw))
    except (ValueError, TypeError):
        return {"status": "invalid_payload"}

    case = session.get(RecoveryCase, case_id)

    if case is None:
        return {"status": "missing_recovery_case"}

    if case.status != RecoveryCaseStatus.ELIGIBLE:
        return {
            "status": "ignored",
            "reason": f"case_status_is_{case.status.value}",
        }

    v = case.version

    try:
        rowcount = atomic_transition_recovery_case(
            session,
            case.id,
            case.status,
            v,
            RecoveryCaseStatus.ANALYSING,
        )
    except InvalidStateTransition:
        return {
            "status": "ignored",
            "reason": "invalid_state_transition",
        }

    if rowcount == 0:
        return {
            "status": "ignored",
            "reason": "state_conflict_or_stale_job",
        }

    v += 1
    current_status = RecoveryCaseStatus.ANALYSING

    engine_decision = evaluate_recovery(
        case.amount_minor,
        case.failure_category,
    )

    policy = get_or_create_default_policy(
        session,
        case.merchant_id,
    )

    policy_input = build_policy_input(
        session=session,
        case=case,
        candidate_action=engine_decision.action,
        current_status=current_status,
    )

    limits = policy_limits_from(policy)

    policy_decision = evaluate_policy(
        limits=limits,
        policy_input=policy_input,
        candidate_delay_hours=engine_decision.delay_hours,
    )

    final_action = policy_decision.final_action
    attempt_number = 1

    idempotency_key = recovery_action_idempotency_key(
        case.id,
        final_action,
        attempt_number,
    )

    action, created = create_recovery_action_idempotent(
        session,
        merchant_id=case.merchant_id,
        recovery_case_id=case.id,
        action_type=final_action,
        idempotency_key=idempotency_key,
        attempt_number=attempt_number,
        status=RecoveryActionStatus.APPROVED,
    )

    if not created:
        return {
            "status": "ignored",
            "reason": "action_already_exists",
        }

    rowcount = atomic_transition_recovery_case(
        session,
        case.id,
        current_status,
        v,
        RecoveryCaseStatus.ACTION_SELECTED,
    )

    if rowcount == 0:
        return {
            "status": "ignored",
            "reason": "state_conflict_during_selection",
        }

    v += 1

    if final_action == RecoveryActionType.STOP:
        rowcount = atomic_transition_recovery_case(
            session,
            case.id,
            RecoveryCaseStatus.ACTION_SELECTED,
            v,
            RecoveryCaseStatus.STOPPED,
        )
        final_status = RecoveryCaseStatus.STOPPED

    elif final_action == RecoveryActionType.ESCALATE:
        rowcount = atomic_transition_recovery_case(
            session,
            case.id,
            RecoveryCaseStatus.ACTION_SELECTED,
            v,
            RecoveryCaseStatus.ESCALATED,
        )
        final_status = RecoveryCaseStatus.ESCALATED

    else:
        if final_action == RecoveryActionType.WAIT:
            delay_hours = policy_decision.delay_hours

            if delay_hours is None:
                delay_hours = engine_decision.delay_hours or 24.0

            next_action_at = utcnow() + timedelta(hours=delay_hours)
        else:
            next_action_at = utcnow()

        rowcount = _atomic_transition_with_next_action_at(
            session,
            case.id,
            RecoveryCaseStatus.ACTION_SELECTED,
            v,
            RecoveryCaseStatus.ACTION_SCHEDULED,
            next_action_at,
        )

        final_status = RecoveryCaseStatus.ACTION_SCHEDULED

    if rowcount == 0:
        return {
            "status": "ignored",
            "reason": "state_conflict_during_final_transition",
        }

    v += 1

    _insert_decision_audit(
        session=session,
        case=case,
        outbox_event_id=str(outbox.id),
        engine_action=engine_decision.action,
        final_action=final_action,
        policy_approved=policy_decision.approved,
        policy_reason=policy_decision.reason,
        final_status=final_status,
    )

    return {
        "status": "processed",
        "recovery_case_id": str(case.id),
        "engine_action": engine_decision.action.value,
        "final_action": final_action.value,
        "policy_approved": policy_decision.approved,
        "policy_reason": policy_decision.reason,
        "final_status": final_status.value,
    }


def _process_outbox_event(outbox_event_id: str) -> dict:
    try:
        outbox_id = UUID(outbox_event_id)
    except ValueError:
        return {"status": "invalid_outbox_id"}

    SessionLocal = get_session_factory()

    with SessionLocal() as session:
        with session.begin():
            outbox = session.get(OutboxEvent, outbox_id)

            if outbox is None:
                return {"status": "missing_outbox_event"}

            if outbox.event_type == "recovery_case.eligible":
                return _handle_recovery_case_eligible(session, outbox)

            return {
                "status": "ignored",
                "reason": "unsupported_event_type",
                "event_type": outbox.event_type,
            }


@celery_app.task(
    bind=True,
    name="recovery.process_outbox_event",
    max_retries=5,
)
def process_outbox_event(self, outbox_event_id: str):
    logger.info(
        "task_started",
        task_name="process_outbox_event",
        outbox_event_id=outbox_event_id,
    )

    try:
        result = _process_outbox_event(outbox_event_id)

        logger.info(
            "task_completed",
            task_name="process_outbox_event",
            outbox_event_id=outbox_event_id,
            result_status=result.get("status"),
        )

        return result

    except (OperationalError, DBAPIError) as exc:
        retries = self.request.retries or 0
        delay = exponential_backoff_with_jitter(retries)

        logger.warning(
            "task_retrying",
            task_name="process_outbox_event",
            outbox_event_id=outbox_event_id,
            retry_number=retries,
            delay_seconds=delay,
            error=str(exc),
        )

        raise self.retry(exc=exc, countdown=delay)

    except Exception:
        logger.exception(
            "task_failed",
            task_name="process_outbox_event",
            outbox_event_id=outbox_event_id,
        )
        raise
