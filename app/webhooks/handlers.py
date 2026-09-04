from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.domain.money import normalize_currency, validate_amount_minor
from app.domain.recovery import transition_recovery_case
from app.domain.recovery_state import InvalidStateTransition, is_terminal
from app.models import (
    AuditEvent,
    Merchant,
    OutboxEvent,
    Payment,
    RecoveryAction,
    RecoveryCase,
    WebhookEvent,
)
from app.models.enums import (
    OutboxEventStatus,
    PaymentStatus,
    RecoveryActionStatus,
    RecoveryCaseStatus,
    WebhookEventStatus,
)
from .razorpay_schemas import (
    RazorpayPaymentEntity,
    RazorpayWebhook,
    extract_payment_entity,
)


SUPPORTED_EVENTS = {
    "payment.failed",
    "payment.captured",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def classify_failure(error_code: Optional[str]) -> str:
    if not error_code:
        return "unknown"

    code = error_code.upper()

    if "EXPIRED" in code:
        return "expired_instrument"

    if "INSUFFICIENT" in code:
        return "insufficient_funds"

    if "NETWORK" in code or "TIMEOUT" in code:
        return "temporary_network"

    return "issuer_failure"


def insert_audit(
    session: Session,
    merchant_id: uuid.UUID,
    entity_type: str,
    entity_id: str,
    event_type: str,
    correlation_id: Optional[str],
    payload: dict,
) -> None:
    audit = AuditEvent(
        merchant_id=merchant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        actor="webhook",
        correlation_id=correlation_id,
        payload=payload,
    )

    session.add(audit)
    session.flush()


def insert_outbox_if_missing(
    session: Session,
    merchant_id: uuid.UUID,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    idempotency_key: str,
    payload: dict,
) -> OutboxEvent:
    existing = session.execute(
        select(OutboxEvent).where(
            OutboxEvent.idempotency_key == idempotency_key
        )
    ).scalar_one_or_none()

    if existing:
        return existing

    outbox = OutboxEvent(
        merchant_id=merchant_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=payload,
        idempotency_key=idempotency_key,
        status=OutboxEventStatus.PENDING,
    )

    session.add(outbox)
    session.flush()

    return outbox


def get_payment_by_provider(
    session: Session,
    merchant_id: uuid.UUID,
    provider_payment_id: str,
) -> Optional[Payment]:
    return session.execute(
        select(Payment).where(
            Payment.merchant_id == merchant_id,
            Payment.provider == "razorpay",
            Payment.provider_payment_id == provider_payment_id,
        )
    ).scalar_one_or_none()


def get_recovery_case_by_payment(
    session: Session,
    payment_id: uuid.UUID,
) -> Optional[RecoveryCase]:
    return session.execute(
        select(RecoveryCase).where(
            RecoveryCase.payment_id == payment_id
        )
    ).scalar_one_or_none()


def handle_payment_failed(
    session: Session,
    merchant: Merchant,
    entity: RazorpayPaymentEntity,
    amount_minor: int,
    currency: str,
    correlation_id: Optional[str],
) -> dict:
    payment = get_payment_by_provider(
        session,
        merchant.id,
        entity.id,
    )

    if payment and payment.status == PaymentStatus.CAPTURED:
        return {
            "outcome": "ignored_already_captured",
            "payment_id": str(payment.id),
        }

    if payment is None:
        payment = Payment(
            merchant_id=merchant.id,
            provider="razorpay",
            provider_payment_id=entity.id,
            status=PaymentStatus.FAILED,
            amount_minor=amount_minor,
            currency=currency,
            failure_code=entity.error_code,
            failure_reason=entity.error_description,
            failed_at=utcnow(),
        )

        session.add(payment)
        session.flush()
    else:
        payment.status = PaymentStatus.FAILED
        payment.amount_minor = amount_minor
        payment.currency = currency
        payment.failure_code = entity.error_code
        payment.failure_reason = entity.error_description
        payment.failed_at = utcnow()
        session.flush()

    case = get_recovery_case_by_payment(session, payment.id)

    if case is None:
        case = RecoveryCase(
            merchant_id=merchant.id,
            payment_id=payment.id,
            status=RecoveryCaseStatus.FAILED,
            amount_minor=payment.amount_minor,
            currency=payment.currency,
            failure_category=classify_failure(entity.error_code),
        )

        session.add(case)
        session.flush()

        transition_recovery_case(case, RecoveryCaseStatus.ELIGIBLE)
        session.flush()

        insert_audit(
            session=session,
            merchant_id=merchant.id,
            entity_type="recovery_case",
            entity_id=str(case.id),
            event_type="recovery_case.eligible",
            correlation_id=correlation_id,
            payload={
                "payment_id": str(payment.id),
                "provider_payment_id": payment.provider_payment_id,
                "from_status": RecoveryCaseStatus.FAILED.value,
                "to_status": RecoveryCaseStatus.ELIGIBLE.value,
                "amount_minor": case.amount_minor,
                "currency": case.currency,
            },
        )

        insert_outbox_if_missing(
            session=session,
            merchant_id=merchant.id,
            aggregate_type="recovery_case",
            aggregate_id=str(case.id),
            event_type="recovery_case.eligible",
            idempotency_key=f"recovery_case.eligible:{case.id}",
            payload={
                "merchant_id": str(merchant.id),
                "payment_id": str(payment.id),
                "recovery_case_id": str(case.id),
                "amount_minor": case.amount_minor,
                "currency": case.currency,
            },
        )

        return {
            "outcome": "recovery_case_created",
            "recovery_case_id": str(case.id),
        }

    if case.status == RecoveryCaseStatus.FAILED:
        transition_recovery_case(case, RecoveryCaseStatus.ELIGIBLE)
        session.flush()

        insert_audit(
            session=session,
            merchant_id=merchant.id,
            entity_type="recovery_case",
            entity_id=str(case.id),
            event_type="recovery_case.eligible",
            correlation_id=correlation_id,
            payload={
                "payment_id": str(payment.id),
                "from_status": RecoveryCaseStatus.FAILED.value,
                "to_status": RecoveryCaseStatus.ELIGIBLE.value,
            },
        )

        insert_outbox_if_missing(
            session=session,
            merchant_id=merchant.id,
            aggregate_type="recovery_case",
            aggregate_id=str(case.id),
            event_type="recovery_case.eligible",
            idempotency_key=f"recovery_case.eligible:{case.id}",
            payload={
                "merchant_id": str(merchant.id),
                "payment_id": str(payment.id),
                "recovery_case_id": str(case.id),
                "amount_minor": case.amount_minor,
                "currency": case.currency,
            },
        )

        return {
            "outcome": "recovery_case_activated",
            "recovery_case_id": str(case.id),
        }

    return {
        "outcome": "recovery_case_already_exists",
        "recovery_case_id": str(case.id),
    }


def handle_payment_captured(
    session: Session,
    merchant: Merchant,
    entity: RazorpayPaymentEntity,
    amount_minor: int,
    currency: str,
    correlation_id: Optional[str],
) -> dict:
    payment = get_payment_by_provider(
        session,
        merchant.id,
        entity.id,
    )

    if payment is None:
        payment = Payment(
            merchant_id=merchant.id,
            provider="razorpay",
            provider_payment_id=entity.id,
            status=PaymentStatus.CAPTURED,
            amount_minor=amount_minor,
            currency=currency,
            captured_at=utcnow(),
        )

        session.add(payment)
        session.flush()
    else:
        if payment.status != PaymentStatus.CAPTURED:
            payment.status = PaymentStatus.CAPTURED
            payment.captured_at = utcnow()
            session.flush()

    case = get_recovery_case_by_payment(session, payment.id)

    if case is None:
        return {
            "outcome": "payment_captured_no_recovery_case",
            "payment_id": str(payment.id),
        }

    if is_terminal(case.status):
        return {
            "outcome": "case_already_terminal",
            "recovery_case_id": str(case.id),
        }

    try:
        transition_recovery_case(case, RecoveryCaseStatus.RECOVERED)
    except InvalidStateTransition:
        return {
            "outcome": "transition_not_allowed",
            "recovery_case_id": str(case.id),
        }

    session.execute(
        update(RecoveryAction)
        .where(
            RecoveryAction.recovery_case_id == case.id,
            RecoveryAction.status.in_(
                [
                    RecoveryActionStatus.PENDING,
                    RecoveryActionStatus.APPROVED,
                    RecoveryActionStatus.EXECUTING,
                ]
            ),
        )
        .values(
            status=RecoveryActionStatus.CANCELLED,
            updated_at=utcnow(),
        )
        .execution_options(synchronize_session=False)
    )

    insert_audit(
        session=session,
        merchant_id=merchant.id,
        entity_type="recovery_case",
        entity_id=str(case.id),
        event_type="recovery_case.recovered",
        correlation_id=correlation_id,
        payload={
            "payment_id": str(payment.id),
            "provider_payment_id": payment.provider_payment_id,
            "to_status": RecoveryCaseStatus.RECOVERED.value,
        },
    )

    insert_outbox_if_missing(
        session=session,
        merchant_id=merchant.id,
        aggregate_type="recovery_case",
        aggregate_id=str(case.id),
        event_type="recovery_case.recovered",
        idempotency_key=f"recovery_case.recovered:{case.id}",
        payload={
            "merchant_id": str(merchant.id),
            "payment_id": str(payment.id),
            "recovery_case_id": str(case.id),
        },
    )

    return {
        "outcome": "recovery_case_recovered",
        "recovery_case_id": str(case.id),
    }


def process_razorpay_event(
    session: Session,
    merchant: Merchant,
    webhook: WebhookEvent,
    event: RazorpayWebhook,
    correlation_id: Optional[str],
) -> dict:
    if event.event not in SUPPORTED_EVENTS:
        webhook.status = WebhookEventStatus.IGNORED
        return {
            "status": "ignored",
            "reason": "unsupported_event",
        }

    entity = extract_payment_entity(event)

    amount_minor = validate_amount_minor(entity.amount)
    currency = normalize_currency(entity.currency)

    if event.event == "payment.failed":
        result = handle_payment_failed(
            session=session,
            merchant=merchant,
            entity=entity,
            amount_minor=amount_minor,
            currency=currency,
            correlation_id=correlation_id,
        )
    else:
        result = handle_payment_captured(
            session=session,
            merchant=merchant,
            entity=entity,
            amount_minor=amount_minor,
            currency=currency,
            correlation_id=correlation_id,
        )

    webhook.status = WebhookEventStatus.PROCESSED

    return {
        "status": "accepted",
        **result,
    }