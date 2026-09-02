import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.domain.recovery import transition_recovery_case
from app.domain.recovery_state import InvalidStateTransition
from app.models import (
    AuditEvent,
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


def create_merchant(session):
    merchant = Merchant(name="Test Merchant")
    session.add(merchant)
    session.flush()
    return merchant


def create_failed_payment(session, merchant, provider_payment_id=None):
    payment = Payment(
        merchant_id=merchant.id,
        provider="razorpay",
        provider_payment_id=provider_payment_id or f"pay_{uuid.uuid4().hex}",
        status=PaymentStatus.FAILED,
        amount_minor=7999,
        currency="INR",
        failure_code="issuer_unavailable",
        failure_reason="Temporary issuer failure",
        failed_at=datetime.now(timezone.utc),
    )

    session.add(payment)
    session.flush()
    return payment


def create_recovery_case(session, merchant, payment):
    case = RecoveryCase(
        merchant_id=merchant.id,
        payment_id=payment.id,
        status=RecoveryCaseStatus.FAILED,
        amount_minor=payment.amount_minor,
        currency=payment.currency,
        failure_category="temporary_network",
    )

    session.add(case)
    session.flush()
    return case


def test_create_core_recovery_records(db_session):
    merchant = create_merchant(db_session)
    payment = create_failed_payment(db_session, merchant)
    case = create_recovery_case(db_session, merchant, payment)

    action = RecoveryAction(
        merchant_id=merchant.id,
        recovery_case_id=case.id,
        action_type=RecoveryActionType.CREATE_PAYMENT_LINK,
        status=RecoveryActionStatus.PENDING,
        idempotency_key=f"action_{uuid.uuid4().hex}",
        attempt_number=1,
    )

    audit = AuditEvent(
        merchant_id=merchant.id,
        entity_type="recovery_case",
        entity_id=str(case.id),
        event_type="recovery_case.created",
        payload={
            "status": case.status.value,
            "amount_minor": case.amount_minor,
            "currency": case.currency,
        },
    )

    db_session.add_all([action, audit])
    db_session.flush()

    assert merchant.id is not None
    assert payment.id is not None
    assert case.id is not None
    assert action.id is not None
    assert audit.id is not None

    assert payment.amount_minor == 7999
    assert case.version == 1


def test_duplicate_provider_payment_id_rejected(db_session):
    merchant = create_merchant(db_session)

    create_failed_payment(
        db_session,
        merchant,
        provider_payment_id="pay_duplicate",
    )

    # We wrap the function call because it contains the flush()
    # that triggers the database constraint violation.
    with pytest.raises(IntegrityError):
        create_failed_payment(
            db_session,
            merchant,
            provider_payment_id="pay_duplicate",
        )

    db_session.rollback()


def test_negative_amount_rejected(db_session):
    merchant = create_merchant(db_session)

    payment = Payment(
        merchant_id=merchant.id,
        provider="razorpay",
        provider_payment_id=f"pay_{uuid.uuid4().hex}",
        status=PaymentStatus.FAILED,
        amount_minor=-1,
        currency="INR",
    )

    db_session.add(payment)

    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()


def test_invalid_currency_rejected(db_session):
    merchant = create_merchant(db_session)

    payment = Payment(
        merchant_id=merchant.id,
        provider="razorpay",
        provider_payment_id=f"pay_{uuid.uuid4().hex}",
        status=PaymentStatus.FAILED,
        amount_minor=7999,
        currency="inr",
    )

    db_session.add(payment)

    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()


def test_duplicate_recovery_case_for_same_payment_rejected(db_session):
    merchant = create_merchant(db_session)
    payment = create_failed_payment(db_session, merchant)

    create_recovery_case(db_session, merchant, payment)

    duplicate_case = RecoveryCase(
        merchant_id=merchant.id,
        payment_id=payment.id,
        status=RecoveryCaseStatus.FAILED,
        amount_minor=payment.amount_minor,
        currency=payment.currency,
    )

    db_session.add(duplicate_case)

    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()


def test_duplicate_action_idempotency_key_rejected(db_session):
    merchant = create_merchant(db_session)
    payment = create_failed_payment(db_session, merchant)
    case = create_recovery_case(db_session, merchant, payment)

    idempotency_key = f"action_{uuid.uuid4().hex}"

    action_one = RecoveryAction(
        merchant_id=merchant.id,
        recovery_case_id=case.id,
        action_type=RecoveryActionType.CREATE_PAYMENT_LINK,
        status=RecoveryActionStatus.PENDING,
        idempotency_key=idempotency_key,
        attempt_number=1,
    )

    db_session.add(action_one)
    db_session.flush()

    action_two = RecoveryAction(
        merchant_id=merchant.id,
        recovery_case_id=case.id,
        action_type=RecoveryActionType.CREATE_PAYMENT_LINK,
        status=RecoveryActionStatus.PENDING,
        idempotency_key=idempotency_key,
        attempt_number=2,
    )

    db_session.add(action_two)

    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()


def test_state_transition_updates_version(db_session):
    merchant = create_merchant(db_session)
    payment = create_failed_payment(db_session, merchant)
    case = create_recovery_case(db_session, merchant, payment)

    old_version = case.version

    transition_recovery_case(case, RecoveryCaseStatus.ELIGIBLE)
    db_session.flush()

    assert case.status == RecoveryCaseStatus.ELIGIBLE
    assert case.version == old_version + 1


def test_terminal_state_cannot_regress(db_session):
    merchant = create_merchant(db_session)
    payment = create_failed_payment(db_session, merchant)
    case = create_recovery_case(db_session, merchant, payment)

    case.status = RecoveryCaseStatus.RECOVERED
    db_session.flush()

    with pytest.raises(InvalidStateTransition):
        transition_recovery_case(case, RecoveryCaseStatus.WAITING)