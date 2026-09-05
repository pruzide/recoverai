import uuid

import pytest

from app.config import settings
from app.models import (
    Merchant,
    Payment,
    RecoveryAction,
    RecoveryCase,
)
from app.models.enums import (
    PaymentStatus,
    RecoveryActionStatus,
    RecoveryActionType,
    RecoveryCaseStatus,
)
from app.services.action_executor import execute_scheduled_action_from_outbox


@pytest.fixture(autouse=True)
def force_mock_razorpay(monkeypatch):
    monkeypatch.setattr(settings, "razorpay_use_mock", True)


def create_scheduled_case_and_action(db_session):
    merchant = Merchant(name="Executor Merchant")
    db_session.add(merchant)
    db_session.flush()

    payment = Payment(
        merchant_id=merchant.id,
        provider="razorpay",
        provider_payment_id=f"pay_{uuid.uuid4().hex}",
        status=PaymentStatus.FAILED,
        amount_minor=5_000,
        currency="INR",
    )
    db_session.add(payment)
    db_session.flush()

    case = RecoveryCase(
        merchant_id=merchant.id,
        payment_id=payment.id,
        status=RecoveryCaseStatus.ACTION_SCHEDULED,
        amount_minor=payment.amount_minor,
        currency=payment.currency,
        version=3,
    )
    db_session.add(case)
    db_session.flush()

    action = RecoveryAction(
        merchant_id=merchant.id,
        recovery_case_id=case.id,
        action_type=RecoveryActionType.CREATE_PAYMENT_LINK,
        status=RecoveryActionStatus.APPROVED,
        idempotency_key=f"recovery_action:{case.id}:CREATE_PAYMENT_LINK:1",
        attempt_number=1,
    )
    db_session.add(action)
    db_session.commit()

    return case, action


def test_executor_creates_mock_payment_link_and_moves_case_to_waiting(db_session):
    case, action = create_scheduled_case_and_action(db_session)

    result = execute_scheduled_action_from_outbox(
        {
            "recovery_action_id": str(action.id),
        }
    )

    assert result["status"] == "executed"
    assert result["action_type"] == RecoveryActionType.CREATE_PAYMENT_LINK.value
    assert result["provider_reference"] is not None

    db_session.expire_all()

    refreshed_case = db_session.get(RecoveryCase, case.id)
    refreshed_action = db_session.get(RecoveryAction, action.id)

    assert refreshed_case.status == RecoveryCaseStatus.WAITING
    assert refreshed_action.status == RecoveryActionStatus.EXECUTED
    assert refreshed_action.provider_reference is not None


def test_executor_cancels_action_when_case_already_recovered(db_session):
    case, action = create_scheduled_case_and_action(db_session)

    case.status = RecoveryCaseStatus.RECOVERED
    db_session.commit()

    result = execute_scheduled_action_from_outbox(
        {
            "recovery_action_id": str(action.id),
        }
    )

    assert result["status"] == "cancelled"

    db_session.expire_all()

    refreshed_case = db_session.get(RecoveryCase, case.id)
    refreshed_action = db_session.get(RecoveryAction, action.id)

    assert refreshed_case.status == RecoveryCaseStatus.RECOVERED
    assert refreshed_action.status == RecoveryActionStatus.CANCELLED