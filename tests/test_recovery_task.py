import uuid

from sqlalchemy import select

from app.models import (
    AuditEvent,
    Merchant,
    OutboxEvent,
    Payment,
    RecoveryCase,
)
from app.models.enums import (
    OutboxEventStatus,
    PaymentStatus,
    RecoveryCaseStatus,
)
from app.tasks.recovery import process_outbox_event


def create_eligible_case_with_outbox(db_session):
    merchant = Merchant(name="Task Merchant")
    db_session.add(merchant)
    db_session.flush()

    payment = Payment(
        merchant_id=merchant.id,
        provider="razorpay",
        provider_payment_id=f"pay_{uuid.uuid4().hex}",
        status=PaymentStatus.FAILED,
        amount_minor=5000,
        currency="INR",
    )
    db_session.add(payment)
    db_session.flush()

    case = RecoveryCase(
        merchant_id=merchant.id,
        payment_id=payment.id,
        status=RecoveryCaseStatus.ELIGIBLE,
        amount_minor=payment.amount_minor,
        currency=payment.currency,
        version=2,
    )
    db_session.add(case)
    db_session.flush()

    outbox = OutboxEvent(
        merchant_id=merchant.id,
        aggregate_type="recovery_case",
        aggregate_id=str(case.id),
        event_type="recovery_case.eligible",
        payload={
            "recovery_case_id": str(case.id),
        },
        idempotency_key=f"recovery_case.eligible:{case.id}",
        status=OutboxEventStatus.PUBLISHED,
    )
    db_session.add(outbox)
    db_session.commit()

    return case, outbox


def test_task_transitions_eligible_case_to_analysing(db_session):
    case, outbox = create_eligible_case_with_outbox(db_session)

    result = process_outbox_event.apply(args=[str(outbox.id)]).get()

    assert result["status"] == "processed"
    assert result["new_status"] == RecoveryCaseStatus.ANALYSING.value

    db_session.expire_all()

    refreshed_case = db_session.get(RecoveryCase, case.id)

    assert refreshed_case.status == RecoveryCaseStatus.ANALYSING


def test_task_ignores_already_processed_case(db_session):
    case, outbox = create_eligible_case_with_outbox(db_session)

    first = process_outbox_event.apply(args=[str(outbox.id)]).get()
    second = process_outbox_event.apply(args=[str(outbox.id)]).get()

    assert first["status"] == "processed"
    assert second["status"] == "ignored"

    audits = db_session.execute(
        select(AuditEvent).where(
            AuditEvent.event_type == "recovery_case.analysis_started"
        )
    ).scalars().all()

    assert len(audits) == 1


def test_task_handles_invalid_outbox_id():
    result = process_outbox_event.apply(args=["not-a-uuid"]).get()

    assert result["status"] == "invalid_outbox_id"
