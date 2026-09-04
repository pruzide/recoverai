import uuid

import pytest
from sqlalchemy import select

from app.domain.recovery_state import InvalidStateTransition
from app.models import (
    Merchant,
    Payment,
    RecoveryAction,
    RecoveryCase,
)
from app.models.enums import (
    PaymentStatus,
    RecoveryActionType,
    RecoveryCaseStatus,
)
from app.services.recovery_actions import (
    create_recovery_action_idempotent,
    recovery_action_idempotency_key,
)
from app.services.recovery_cases import atomic_transition_recovery_case


def create_case(db_session, status=RecoveryCaseStatus.ELIGIBLE, version=1):
    merchant = Merchant(name="Concurrency Merchant")
    db_session.add(merchant)
    db_session.flush()

    payment = Payment(
        merchant_id=merchant.id,
        provider="razorpay",
        provider_payment_id=f"pay_{uuid.uuid4().hex}",
        status=PaymentStatus.FAILED,
        amount_minor=4200,
        currency="INR",
    )
    db_session.add(payment)
    db_session.flush()

    case = RecoveryCase(
        merchant_id=merchant.id,
        payment_id=payment.id,
        status=status,
        amount_minor=payment.amount_minor,
        currency=payment.currency,
        version=version,
    )
    db_session.add(case)
    db_session.commit()

    return case


def test_atomic_transition_success(db_session):
    case = create_case(db_session)

    old_version = case.version

    rowcount = atomic_transition_recovery_case(
        session=db_session,
        case_id=case.id,
        expected_status=case.status,
        expected_version=case.version,
        new_status=RecoveryCaseStatus.ANALYSING,
    )

    db_session.commit()

    assert rowcount == 1

    db_session.expire_all()

    refreshed = db_session.get(RecoveryCase, case.id)

    assert refreshed.status == RecoveryCaseStatus.ANALYSING
    assert refreshed.version == old_version + 1


def test_atomic_transition_with_stale_version_fails(db_session):
    case = create_case(db_session)

    rowcount = atomic_transition_recovery_case(
        session=db_session,
        case_id=case.id,
        expected_status=RecoveryCaseStatus.ELIGIBLE,
        expected_version=case.version + 999,
        new_status=RecoveryCaseStatus.ANALYSING,
    )

    db_session.commit()

    assert rowcount == 0

    db_session.expire_all()

    refreshed = db_session.get(RecoveryCase, case.id)

    assert refreshed.status == RecoveryCaseStatus.ELIGIBLE
    assert refreshed.version == case.version


def test_invalid_transition_raises(db_session):
    case = create_case(db_session)

    with pytest.raises(InvalidStateTransition):
        atomic_transition_recovery_case(
            session=db_session,
            case_id=case.id,
            expected_status=RecoveryCaseStatus.ELIGIBLE,
            expected_version=case.version,
            new_status=RecoveryCaseStatus.WAITING,
        )


def test_idempotent_action_creation(db_session):
    case = create_case(db_session)

    action_type = RecoveryActionType.CREATE_PAYMENT_LINK
    attempt_number = 1

    idempotency_key = recovery_action_idempotency_key(
        case.id,
        action_type,
        attempt_number,
    )

    action_one, created_one = create_recovery_action_idempotent(
        db_session,
        merchant_id=case.merchant_id,
        recovery_case_id=case.id,
        action_type=action_type,
        idempotency_key=idempotency_key,
        attempt_number=attempt_number,
    )

    db_session.commit()

    action_two, created_two = create_recovery_action_idempotent(
        db_session,
        merchant_id=case.merchant_id,
        recovery_case_id=case.id,
        action_type=action_type,
        idempotency_key=idempotency_key,
        attempt_number=attempt_number,
    )

    db_session.commit()

    assert created_one is True
    assert created_two is False
    assert action_one.id == action_two.id

    actions = db_session.execute(
        select(RecoveryAction).where(
            RecoveryAction.recovery_case_id == case.id
        )
    ).scalars().all()

    assert len(actions) == 1


def test_idempotency_keys_are_stable():
    case_id = uuid.uuid4()

    key_one = recovery_action_idempotency_key(
        case_id,
        RecoveryActionType.CREATE_PAYMENT_LINK,
        1,
    )

    key_two = recovery_action_idempotency_key(
        case_id,
        RecoveryActionType.CREATE_PAYMENT_LINK,
        1,
    )

    key_three = recovery_action_idempotency_key(
        case_id,
        RecoveryActionType.CREATE_PAYMENT_LINK,
        2,
    )

    assert key_one == key_two
    assert key_one != key_three
