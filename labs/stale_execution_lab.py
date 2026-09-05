import sys
import uuid
from pathlib import Path
from sqlalchemy import text

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.db import get_session_factory
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


def main():
    SessionLocal = get_session_factory()

    with SessionLocal() as session:
        with session.begin():
            merchant = Merchant(name="Stale Execution Lab")
            session.add(merchant)
            session.flush()

            payment = Payment(
                merchant_id=merchant.id,
                provider="razorpay",
                provider_payment_id=f"pay_lab_{uuid.uuid4().hex}",
                status=PaymentStatus.FAILED,
                amount_minor=5_000,
                currency="INR",
            )
            session.add(payment)
            session.flush()

            case = RecoveryCase(
                merchant_id=merchant.id,
                payment_id=payment.id,
                status=RecoveryCaseStatus.ACTION_SCHEDULED,
                amount_minor=payment.amount_minor,
                currency=payment.currency,
                version=3,
            )
            session.add(case)
            session.flush()

            action = RecoveryAction(
                merchant_id=merchant.id,
                recovery_case_id=case.id,
                action_type=RecoveryActionType.CREATE_PAYMENT_LINK,
                status=RecoveryActionStatus.APPROVED,
                idempotency_key=f"lab:{uuid.uuid4().hex}",
                attempt_number=1,
            )
            session.add(action)
            session.flush()

            merchant_id = merchant.id
            payment_id = payment.id
            case_id = case.id
            action_id = action.id

    with SessionLocal() as session:
        with session.begin():
            case = session.get(RecoveryCase, case_id)
            case.status = RecoveryCaseStatus.RECOVERED

    result = execute_scheduled_action_from_outbox(
        {
            "recovery_action_id": str(action_id),
        }
    )

    print("Executor result:", result)

    with SessionLocal() as session:
        case = session.get(RecoveryCase, case_id)
        action = session.get(RecoveryAction, action_id)

        print("Case status:", case.status.value)
        print("Action status:", action.status.value)

        assert case.status == RecoveryCaseStatus.RECOVERED
        assert action.status == RecoveryActionStatus.CANCELLED

        with SessionLocal() as session:
            with session.begin():
                session.execute(
                    text("DELETE FROM recovery_actions WHERE id = :action_id"),
                    {"action_id": str(action_id)},
                )

                session.execute(
                    text("DELETE FROM recovery_cases WHERE id = :case_id"),
                    {"case_id": str(case_id)},
                )

                session.execute(
                    text("DELETE FROM payments WHERE id = :payment_id"),
                    {"payment_id": str(payment_id)},
                )

                session.execute(
                    text("DELETE FROM merchants WHERE id = :merchant_id"),
                    {"merchant_id": str(merchant_id)},
                )

        print("LAB PASSED: stale execution was cancelled.")


if __name__ == "__main__":
    main()