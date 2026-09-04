import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.models import (
    Merchant,
    OutboxEvent,
    Payment,
    RecoveryAction,
    RecoveryCase,
)
from app.models.enums import (
    OutboxEventStatus,
    PaymentStatus,
    RecoveryActionType,
    RecoveryCaseStatus,
)
from app.tasks.recovery import process_outbox_event


def create_case_with_outbox(
    db_session,
    amount=5000,
    category="expired_instrument",
    status=RecoveryCaseStatus.ELIGIBLE,
):
    merchant = Merchant(name="Engine Merchant")
    db_session.add(merchant)
    db_session.flush()

    payment = Payment(
        merchant_id=merchant.id,
        provider="razorpay",
        provider_payment_id=f"pay_{uuid.uuid4().hex}",
        status=PaymentStatus.FAILED,
        amount_minor=amount,
        currency="INR",
        failure_code=category,
    )
    db_session.add(payment)
    db_session.flush()

    case = RecoveryCase(
        merchant_id=merchant.id,
        payment_id=payment.id,
        status=status,
        amount_minor=amount,
        currency="INR",
        failure_category=category,
        version=1,
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


def test_invalid_outbox_id():
    result = process_outbox_event.apply(args=["not-a-uuid"]).get()

    assert result["status"] == "invalid_outbox_id"


def test_task_selects_payment_link_for_expired(db_session):
    case, outbox = create_case_with_outbox(
        db_session,
        amount=5000,
        category="expired_instrument",
    )

    result = process_outbox_event.apply(args=[str(outbox.id)]).get()

    assert result["status"] == "processed"
    assert result["action"] == RecoveryActionType.CREATE_PAYMENT_LINK.value
    assert result["final_status"] == RecoveryCaseStatus.ACTION_SELECTED.value

    db_session.expire_all()

    refreshed_case = db_session.get(RecoveryCase, case.id)

    assert refreshed_case.status == RecoveryCaseStatus.ACTION_SELECTED
    assert refreshed_case.version == 3

    actions = db_session.execute(
        select(RecoveryAction).where(
            RecoveryAction.recovery_case_id == case.id
        )
    ).scalars().all()

    assert len(actions) == 1
    assert actions[0].action_type == RecoveryActionType.CREATE_PAYMENT_LINK


def test_task_stops_low_value(db_session):
    case, outbox = create_case_with_outbox(
        db_session,
        amount=500,
        category="expired_instrument",
    )

    result = process_outbox_event.apply(args=[str(outbox.id)]).get()

    assert result["status"] == "processed"
    assert result["action"] == RecoveryActionType.STOP.value
    assert result["final_status"] == RecoveryCaseStatus.STOPPED.value

    db_session.expire_all()

    refreshed_case = db_session.get(RecoveryCase, case.id)

    assert refreshed_case.status == RecoveryCaseStatus.STOPPED
    assert refreshed_case.version == 4

    actions = db_session.execute(
        select(RecoveryAction).where(
            RecoveryAction.recovery_case_id == case.id
        )
    ).scalars().all()

    assert len(actions) == 1
    assert actions[0].action_type == RecoveryActionType.STOP


def test_task_schedules_wait_for_insufficient_funds(db_session):
    case, outbox = create_case_with_outbox(
        db_session,
        amount=5000,
        category="insufficient_funds",
    )

    result = process_outbox_event.apply(args=[str(outbox.id)]).get()

    assert result["status"] == "processed"
    assert result["action"] == RecoveryActionType.WAIT.value
    assert result["final_status"] == RecoveryCaseStatus.ACTION_SCHEDULED.value

    db_session.expire_all()

    refreshed_case = db_session.get(RecoveryCase, case.id)

    assert refreshed_case.status == RecoveryCaseStatus.ACTION_SCHEDULED
    assert refreshed_case.version == 4
    assert refreshed_case.next_action_at is not None
    assert refreshed_case.next_action_at > datetime.now(timezone.utc)

    actions = db_session.execute(
        select(RecoveryAction).where(
            RecoveryAction.recovery_case_id == case.id
        )
    ).scalars().all()

    assert len(actions) == 1
    assert actions[0].action_type == RecoveryActionType.WAIT
    assert actions[0].scheduled_at is not None


def test_task_escalates_issuer_failure(db_session):
    case, outbox = create_case_with_outbox(
        db_session,
        amount=5000,
        category="issuer_failure",
    )

    result = process_outbox_event.apply(args=[str(outbox.id)]).get()

    assert result["status"] == "processed"
    assert result["action"] == RecoveryActionType.ESCALATE.value
    assert result["final_status"] == RecoveryCaseStatus.ESCALATED.value

    db_session.expire_all()

    refreshed_case = db_session.get(RecoveryCase, case.id)

    assert refreshed_case.status == RecoveryCaseStatus.ESCALATED
    assert refreshed_case.version == 4

    actions = db_session.execute(
        select(RecoveryAction).where(
            RecoveryAction.recovery_case_id == case.id
        )
    ).scalars().all()

    assert len(actions) == 1
    assert actions[0].action_type == RecoveryActionType.ESCALATE


def test_task_ignores_non_eligible_case(db_session):
    case, outbox = create_case_with_outbox(
        db_session,
        amount=5000,
        category="expired_instrument",
        status=RecoveryCaseStatus.ANALYSING,
    )

    result = process_outbox_event.apply(args=[str(outbox.id)]).get()

    assert result["status"] == "ignored"
    assert "case_status_is_ANALYSING" in result["reason"]

    db_session.expire_all()

    actions = db_session.execute(
        select(RecoveryAction).where(
            RecoveryAction.recovery_case_id == case.id
        )
    ).scalars().all()

    assert len(actions) == 0