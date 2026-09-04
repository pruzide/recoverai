import uuid

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
    RecoveryActionStatus,
    RecoveryActionType,
    RecoveryCaseStatus,
)
from app.tasks.recovery import process_outbox_event


def create_case_with_outbox(
    db_session,
    amount=5_000,
    category="expired_instrument",
):
    merchant = Merchant(name="Policy Merchant")
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
        status=RecoveryCaseStatus.ELIGIBLE,
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
        payload={"recovery_case_id": str(case.id)},
        idempotency_key=f"recovery_case.eligible:{case.id}",
        status=OutboxEventStatus.PUBLISHED,
    )
    db_session.add(outbox)
    db_session.commit()

    return case, outbox


def add_existing_action(
    db_session,
    case,
    action_type,
    attempt_number,
    status,
):
    action = RecoveryAction(
        merchant_id=case.merchant_id,
        recovery_case_id=case.id,
        action_type=action_type,
        status=status,
        idempotency_key=f"lab:{uuid.uuid4().hex}",
        attempt_number=attempt_number,
    )

    db_session.add(action)
    db_session.commit()


def test_expired_card_payment_link_approved_and_scheduled(db_session):
    case, outbox = create_case_with_outbox(db_session)

    result = process_outbox_event.apply(args=[str(outbox.id)]).get()

    assert result["status"] == "processed"
    assert result["engine_action"] == RecoveryActionType.CREATE_PAYMENT_LINK.value
    assert result["policy_approved"] is True
    assert result["final_action"] == RecoveryActionType.CREATE_PAYMENT_LINK.value
    assert result["final_status"] == RecoveryCaseStatus.ACTION_SCHEDULED.value

    db_session.expire_all()

    refreshed_case = db_session.get(RecoveryCase, case.id)
    assert refreshed_case.status == RecoveryCaseStatus.ACTION_SCHEDULED
    assert refreshed_case.next_action_at is not None

    action = db_session.execute(
        select(RecoveryAction).where(
            RecoveryAction.recovery_case_id == case.id
        )
    ).scalar_one()

    assert action.action_type == RecoveryActionType.CREATE_PAYMENT_LINK
    assert action.status == RecoveryActionStatus.APPROVED


def test_high_value_case_forced_to_escalate(db_session):
    case, outbox = create_case_with_outbox(
        db_session,
        amount=600_000,
        category="expired_instrument",
    )

    result = process_outbox_event.apply(args=[str(outbox.id)]).get()

    assert result["policy_approved"] is False
    assert result["engine_action"] == RecoveryActionType.CREATE_PAYMENT_LINK.value
    assert result["final_action"] == RecoveryActionType.ESCALATE.value
    assert result["final_status"] == RecoveryCaseStatus.ESCALATED.value

    db_session.expire_all()

    refreshed_case = db_session.get(RecoveryCase, case.id)
    assert refreshed_case.status == RecoveryCaseStatus.ESCALATED

    action = db_session.execute(
        select(RecoveryAction).where(
            RecoveryAction.recovery_case_id == case.id
        )
    ).scalar_one()

    assert action.action_type == RecoveryActionType.ESCALATE


def test_active_payment_link_falls_back_to_wait(db_session):
    case, outbox = create_case_with_outbox(
        db_session,
        amount=5_000,
        category="expired_instrument",
    )

    add_existing_action(
        db_session,
        case,
        RecoveryActionType.CREATE_PAYMENT_LINK,
        1,
        RecoveryActionStatus.APPROVED,
    )

    result = process_outbox_event.apply(args=[str(outbox.id)]).get()

    assert result["policy_approved"] is False
    assert result["final_action"] == RecoveryActionType.WAIT.value
    assert result["final_status"] == RecoveryCaseStatus.ACTION_SCHEDULED.value

    db_session.expire_all()

    refreshed_case = db_session.get(RecoveryCase, case.id)
    assert refreshed_case.status == RecoveryCaseStatus.ACTION_SCHEDULED
    assert refreshed_case.next_action_at is not None

    actions = db_session.execute(
        select(RecoveryAction).where(
            RecoveryAction.recovery_case_id == case.id
        )
    ).scalars().all()

    action_types = {action.action_type for action in actions}

    assert RecoveryActionType.CREATE_PAYMENT_LINK in action_types
    assert RecoveryActionType.WAIT in action_types


def test_max_reminders_reached_falls_back_to_stop(db_session):
    case, outbox = create_case_with_outbox(
        db_session,
        amount=5_000,
        category="temporary_network",
    )

    add_existing_action(
        db_session,
        case,
        RecoveryActionType.SEND_REMINDER,
        1,
        RecoveryActionStatus.EXECUTED,
    )

    add_existing_action(
        db_session,
        case,
        RecoveryActionType.SEND_REMINDER,
        2,
        RecoveryActionStatus.EXECUTED,
    )

    result = process_outbox_event.apply(args=[str(outbox.id)]).get()

    assert result["policy_approved"] is False
    assert result["final_action"] == RecoveryActionType.STOP.value
    assert result["final_status"] == RecoveryCaseStatus.STOPPED.value

    db_session.expire_all()

    refreshed_case = db_session.get(RecoveryCase, case.id)
    assert refreshed_case.status == RecoveryCaseStatus.STOPPED
