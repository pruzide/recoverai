from uuid import UUID

import structlog
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db import get_session_factory
from app.domain.policy import evaluate_policy
from app.domain.recovery_state import InvalidStateTransition, is_terminal
from app.integrations.razorpay import RazorpayError, create_payment_link
from app.models import AuditEvent, Payment, RecoveryAction, RecoveryCase
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
from app.services.recovery_cases import (
    atomic_transition_recovery_case,
    utcnow,
)


logger = structlog.get_logger()


def _audit(
    session: Session,
    case: RecoveryCase,
    action: RecoveryAction,
    event_type: str,
    payload: dict,
) -> None:
    audit = AuditEvent(
        merchant_id=case.merchant_id,
        entity_type="recovery_action",
        entity_id=str(action.id),
        event_type=event_type,
        actor="action_executor",
        correlation_id=None,
        payload={
            "recovery_case_id": str(case.id),
            "action_type": action.action_type.value,
            **payload,
        },
    )

    session.add(audit)
    session.flush()


def _atomic_action_transition(
    session: Session,
    action_id: UUID,
    expected_status: RecoveryActionStatus,
    new_status: RecoveryActionStatus,
) -> int:
    result = session.execute(
        update(RecoveryAction)
        .where(
            RecoveryAction.id == action_id,
            RecoveryAction.status == expected_status,
        )
        .values(
            status=new_status,
            updated_at=utcnow(),
        )
    )

    return max(0, result.rowcount)


def _claim_action(session: Session, action_id: UUID) -> dict:
    action = session.get(RecoveryAction, action_id)

    if action is None:
        return {"status": "missing_action"}

    case = session.get(RecoveryCase, action.recovery_case_id)

    if case is None:
        return {"status": "missing_case"}

    payment = session.get(Payment, case.payment_id)

    policy = get_or_create_default_policy(session, case.merchant_id)
    limits = policy_limits_from(policy)

    policy_input = build_policy_input(
        session=session,
        case=case,
        candidate_action=action.action_type,
        current_status=case.status,
        exclude_action_id=action.id,
    )

    policy_decision = evaluate_policy(
        limits=limits,
        policy_input=policy_input,
        candidate_delay_hours=None,
    )

    allowed = (
        not is_terminal(case.status)
        and policy_decision.approved
        and policy_decision.final_action == action.action_type
    )

    if not allowed:
        rowcount = _atomic_action_transition(
            session,
            action.id,
            RecoveryActionStatus.APPROVED,
            RecoveryActionStatus.CANCELLED,
        )

        if rowcount == 1:
            _audit(
                session,
                case,
                action,
                "recovery_action.cancelled",
                {
                    "reason": policy_decision.reason,
                    "case_status": case.status.value,
                },
            )

            if (
                not is_terminal(case.status)
                and case.status == RecoveryCaseStatus.ACTION_SCHEDULED
            ):
                try:
                    atomic_transition_recovery_case(
                        session,
                        case.id,
                        case.status,
                        case.version,
                        RecoveryCaseStatus.STOPPED,
                    )
                except InvalidStateTransition:
                    pass

        return {
            "status": "cancelled",
            "reason": policy_decision.reason,
        }

    if action.status != RecoveryActionStatus.APPROVED:
        return {
            "status": "ignored",
            "reason": f"action_status_is_{action.status.value}",
        }

    rowcount = _atomic_action_transition(
        session,
        action.id,
        RecoveryActionStatus.APPROVED,
        RecoveryActionStatus.EXECUTING,
    )

    if rowcount == 0:
        return {
            "status": "ignored",
            "reason": "action_not_claimable",
        }

    _audit(
        session,
        case,
        action,
        "recovery_action.claimed",
        {
            "case_status": case.status.value,
        },
    )

    return {
        "status": "claimed",
        "action_id": action.id,
        "case_id": case.id,
        "merchant_id": case.merchant_id,
        "action_type": action.action_type,
        "idempotency_key": action.idempotency_key,
        "amount_minor": case.amount_minor,
        "currency": case.currency,
        "original_provider_payment_id": payment.provider_payment_id if payment else None,
    }


def _execute_external(context: dict) -> tuple[str | None, dict]:
    action_type = context["action_type"]

    if action_type == RecoveryActionType.CREATE_PAYMENT_LINK:
        description = "RecoverAI payment link"

        if context.get("original_provider_payment_id"):
            description = (
                f"Recovery payment for {context['original_provider_payment_id']}"
            )

        notes = {
            "recoverai_merchant_id": str(context["merchant_id"]),
            "recoverai_recovery_case_id": str(context["case_id"]),
            "recoverai_recovery_action_id": str(context["action_id"]),
            "recoverai_original_payment_reference": context.get(
                "original_provider_payment_id"
            ),
        }

        result = create_payment_link(
            amount_minor=context["amount_minor"],
            currency=context["currency"],
            description=description,
            reference_id=context["idempotency_key"],
            notes=notes,
        )

        provider_reference = result.get("short_url") or result.get("id")

        return provider_reference, result

    if action_type == RecoveryActionType.SEND_REMINDER:
        provider_reference = f"reminder:{context['action_id']}"

        return provider_reference, {
            "reminder": "simulated_reminder_sent",
        }

    if action_type == RecoveryActionType.WAIT:
        return None, {
            "wait": "completed",
        }

    raise RazorpayError(f"unsupported executable action: {action_type.value}")


def _finalize_success(
    context: dict,
    provider_reference: str | None,
    details: dict,
) -> None:
    SessionLocal = get_session_factory()

    with SessionLocal() as session:
        with session.begin():
            action = session.get(RecoveryAction, context["action_id"])
            case = session.get(RecoveryCase, context["case_id"])

            if action is None or case is None:
                return

            if action.status != RecoveryActionStatus.EXECUTING:
                return

            action.status = RecoveryActionStatus.EXECUTED
            action.executed_at = utcnow()
            action.provider_reference = provider_reference
            action.failure_reason = None

            if case.status == RecoveryCaseStatus.ACTION_SCHEDULED:
                try:
                    atomic_transition_recovery_case(
                        session,
                        case.id,
                        case.status,
                        case.version,
                        RecoveryCaseStatus.WAITING,
                    )
                except InvalidStateTransition:
                    pass

            _audit(
                session,
                case,
                action,
                "recovery_action.executed",
                {
                    "provider_reference": provider_reference,
                    "details": details,
                },
            )


def _finalize_failure(context: dict, error: Exception) -> None:
    SessionLocal = get_session_factory()

    with SessionLocal() as session:
        with session.begin():
            action = session.get(RecoveryAction, context["action_id"])
            case = session.get(RecoveryCase, context["case_id"])

            if action is None or case is None:
                return

            if action.status == RecoveryActionStatus.EXECUTING:
                action.status = RecoveryActionStatus.FAILED
                action.failure_reason = str(error)[:512]

            _audit(
                session,
                case,
                action,
                "recovery_action.failed",
                {
                    "error": str(error),
                },
            )


def execute_scheduled_action_from_outbox(payload: dict) -> dict:
    action_id_raw = payload.get("recovery_action_id")

    try:
        action_id = UUID(str(action_id_raw))
    except (ValueError, TypeError):
        return {"status": "invalid_payload"}

    SessionLocal = get_session_factory()

    with SessionLocal() as session:
        with session.begin():
            claim = _claim_action(session, action_id)

    if claim.get("status") != "claimed":
        return claim

    try:
        provider_reference, details = _execute_external(claim)

    except RazorpayError as exc:
        _finalize_failure(claim, exc)

        return {
            "status": "failed",
            "reason": str(exc),
        }

    except Exception as exc:
        _finalize_failure(claim, exc)
        raise

    _finalize_success(claim, provider_reference, details)

    return {
        "status": "executed",
        "action_type": claim["action_type"].value,
        "provider_reference": provider_reference,
    }