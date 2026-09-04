from datetime import timedelta
from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy import update
from sqlalchemy.exc import DBAPIError, OperationalError

from app.celery_app import celery_app
from app.db import get_session_factory
from app.domain.recovery_engine import evaluate_recovery
from app.domain.recovery_state import InvalidStateTransition
from app.models import AuditEvent, OutboxEvent, RecoveryCase
from app.models.enums import RecoveryActionType, RecoveryCaseStatus
from app.services.recovery_actions import (
    create_recovery_action_idempotent,
    recovery_action_idempotency_key,
)
from app.services.recovery_cases import atomic_transition_recovery_case, utcnow
from app.tasks.backoff import exponential_backoff_with_jitter


logger = structlog.get_logger()


class IgnoredTaskError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _insert_task_audit(
    session,
    case: RecoveryCase,
    outbox_event_id: str,
    from_status: RecoveryCaseStatus,
    to_status: RecoveryCaseStatus,
    decision_reason: Optional[str] = None,
    action_type: Optional[str] = None,
) -> None:
    payload = {
        "outbox_event_id": outbox_event_id,
        "from_status": from_status.value,
        "to_status": to_status.value,
    }

    if decision_reason:
        payload["decision_reason"] = decision_reason

    if action_type:
        payload["action_type"] = action_type

    audit = AuditEvent(
        merchant_id=case.merchant_id,
        entity_type="recovery_case",
        entity_id=str(case.id),
        event_type="recovery_case.processed",
        actor="worker",
        correlation_id=None,
        payload=payload,
    )

    session.add(audit)
    session.flush()


def _handle_recovery_case_eligible(session, outbox: OutboxEvent) -> dict:
    case_id_raw = outbox.payload.get("recovery_case_id")

    try:
        case_id = UUID(str(case_id_raw))
    except (ValueError, TypeError):
        return {
            "status": "invalid_payload",
            "reason": "missing_or_invalid_recovery_case_id",
        }

    case = session.get(RecoveryCase, case_id)

    if case is None:
        return {
            "status": "missing_recovery_case",
            "recovery_case_id": str(case_id_raw),
        }

    if case.status != RecoveryCaseStatus.ELIGIBLE:
        raise IgnoredTaskError(
            f"case_status_is_{case.status.value}"
        )

    v = case.version
    final_status = case.status

    try:
        rowcount = atomic_transition_recovery_case(
            session=session,
            case_id=case.id,
            expected_status=case.status,
            expected_version=v,
            new_status=RecoveryCaseStatus.ANALYSING,
        )
    except InvalidStateTransition:
        raise IgnoredTaskError("invalid_state_transition")

    if rowcount == 0:
        raise IgnoredTaskError("state_conflict_or_stale_job")

    v += 1
    final_status = RecoveryCaseStatus.ANALYSING

    decision = evaluate_recovery(
        amount_minor=case.amount_minor,
        failure_category=case.failure_category,
    )

    action_type = decision.action
    attempt_number = 1

    scheduled_at = None
    if action_type == RecoveryActionType.WAIT:
        scheduled_at = utcnow() + timedelta(hours=decision.delay_hours or 24.0)

    idempotency_key = recovery_action_idempotency_key(
        case.id,
        action_type,
        attempt_number,
    )

    action, created = create_recovery_action_idempotent(
        session,
        merchant_id=case.merchant_id,
        recovery_case_id=case.id,
        action_type=action_type,
        idempotency_key=idempotency_key,
        attempt_number=attempt_number,
        scheduled_at=scheduled_at,
    )

    if not created:
        raise IgnoredTaskError("action_already_exists")

    rowcount = atomic_transition_recovery_case(
        session=session,
        case_id=case.id,
        expected_status=RecoveryCaseStatus.ANALYSING,
        expected_version=v,
        new_status=RecoveryCaseStatus.ACTION_SELECTED,
    )

    if rowcount == 0:
        raise IgnoredTaskError("state_conflict_during_selection")

    v += 1
    final_status = RecoveryCaseStatus.ACTION_SELECTED

    if action_type == RecoveryActionType.STOP:
        rowcount = atomic_transition_recovery_case(
            session=session,
            case_id=case.id,
            expected_status=RecoveryCaseStatus.ACTION_SELECTED,
            expected_version=v,
            new_status=RecoveryCaseStatus.STOPPED,
        )

        if rowcount == 0:
            raise IgnoredTaskError("state_conflict_during_stop")

        v += 1
        final_status = RecoveryCaseStatus.STOPPED

    elif action_type == RecoveryActionType.ESCALATE:
        rowcount = atomic_transition_recovery_case(
            session=session,
            case_id=case.id,
            expected_status=RecoveryCaseStatus.ACTION_SELECTED,
            expected_version=v,
            new_status=RecoveryCaseStatus.ESCALATED,
        )

        if rowcount == 0:
            raise IgnoredTaskError("state_conflict_during_escalation")

        v += 1
        final_status = RecoveryCaseStatus.ESCALATED

    elif action_type == RecoveryActionType.WAIT:
        rowcount = atomic_transition_recovery_case(
            session=session,
            case_id=case.id,
            expected_status=RecoveryCaseStatus.ACTION_SELECTED,
            expected_version=v,
            new_status=RecoveryCaseStatus.ACTION_SCHEDULED,
        )

        if rowcount == 0:
            raise IgnoredTaskError("state_conflict_during_wait_scheduling")

        v += 1
        final_status = RecoveryCaseStatus.ACTION_SCHEDULED

        schedule_result = session.execute(
            update(RecoveryCase)
            .where(RecoveryCase.id == case.id)
            .values(
                next_action_at=scheduled_at,
                updated_at=utcnow(),
            )
        )

        if schedule_result.rowcount == 0:
            raise IgnoredTaskError("failed_to_schedule_wait")

    _insert_task_audit(
        session=session,
        case=case,
        outbox_event_id=str(outbox.id),
        from_status=RecoveryCaseStatus.ELIGIBLE,
        to_status=final_status,
        decision_reason=decision.reason,
        action_type=action_type.value,
    )

    return {
        "status": "processed",
        "recovery_case_id": str(case.id),
        "action": action_type.value,
        "final_status": final_status.value,
        "reason": decision.reason,
    }


def _process_outbox_event(outbox_event_id: str) -> dict:
    try:
        outbox_id = UUID(outbox_event_id)
    except ValueError:
        return {
            "status": "invalid_outbox_id",
        }

    SessionLocal = get_session_factory()

    with SessionLocal() as session:
        try:
            with session.begin():
                outbox = session.get(OutboxEvent, outbox_id)

                if outbox is None:
                    return {
                        "status": "missing_outbox_event",
                    }

                if outbox.event_type == "recovery_case.eligible":
                    return _handle_recovery_case_eligible(session, outbox)

                return {
                    "status": "ignored",
                    "reason": "unsupported_event_type",
                    "event_type": outbox.event_type,
                }

        except IgnoredTaskError as exc:
            return {
                "status": "ignored",
                "reason": exc.reason,
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