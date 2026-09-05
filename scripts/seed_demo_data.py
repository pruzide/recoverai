import sys
from datetime import timedelta
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db import get_session_factory
from app.models import AuditEvent, Merchant, Payment, RecoveryAction, RecoveryCase
from app.models.enums import (
    PaymentStatus,
    RecoveryActionStatus,
    RecoveryActionType,
    RecoveryCaseStatus,
)

CATEGORIES = [
    "expired_instrument",
    "insufficient_funds",
    "temporary_network",
    "issuer_failure",
    "unknown",
]


def utcnow():
    return datetime.now(timezone.utc)


def main():
    SessionLocal = get_session_factory()

    with SessionLocal() as session:
        with session.begin():
            existing = session.execute(
                select(Merchant).where(Merchant.name == "Demo Merchant")
            ).scalar_one_or_none()

            if existing:
                print("Demo Merchant already exists. Skipping seed.")
                print(f"merchant_id={existing.id}")
                return

            merchant = Merchant(name="Demo Merchant")
            session.add(merchant)
            session.flush()

            plan = [
                (RecoveryCaseStatus.RECOVERED, 12),
                (RecoveryCaseStatus.WAITING, 8),
                (RecoveryCaseStatus.ACTION_SCHEDULED, 5),
                (RecoveryCaseStatus.STOPPED, 6),
                (RecoveryCaseStatus.ESCALATED, 4),
            ]

            idx = 0
            for status, count in plan:
                for _ in range(count):
                    idx += 1
                    category = CATEGORIES[idx % len(CATEGORIES)]
                    amount = 50000 + (idx * 7919) % 450000

                    payment = Payment(
                        merchant_id=merchant.id,
                        provider="razorpay",
                        provider_payment_id=f"pay_demo_{idx:04d}",
                        status=PaymentStatus.CAPTURED
                        if status == RecoveryCaseStatus.RECOVERED
                        else PaymentStatus.FAILED,
                        amount_minor=amount,
                        currency="INR",
                        failure_code=category,
                        failed_at=utcnow() - timedelta(hours=idx),
                    )
                    session.add(payment)
                    session.flush()

                    case = RecoveryCase(
                        merchant_id=merchant.id,
                        payment_id=payment.id,
                        status=status,
                        amount_minor=amount,
                        currency="INR",
                        failure_category=category,
                        version=3,
                        next_action_at=utcnow() + timedelta(hours=24)
                        if status == RecoveryCaseStatus.WAITING
                        else None,
                    )
                    session.add(case)
                    session.flush()

                    action_type = (
                        RecoveryActionType.CREATE_PAYMENT_LINK
                        if category == "expired_instrument"
                        else RecoveryActionType.SEND_REMINDER
                        if category == "temporary_network"
                        else RecoveryActionType.WAIT
                        if category == "insufficient_funds"
                        else RecoveryActionType.ESCALATE
                        if category == "issuer_failure"
                        else RecoveryActionType.STOP
                    )

                    action_status = (
                        RecoveryActionStatus.EXECUTED
                        if status
                        in (
                            RecoveryCaseStatus.RECOVERED,
                            RecoveryCaseStatus.WAITING,
                        )
                        else RecoveryActionStatus.CANCELLED
                        if status == RecoveryCaseStatus.STOPPED
                        else RecoveryActionStatus.APPROVED
                    )

                    action = RecoveryAction(
                        merchant_id=merchant.id,
                        recovery_case_id=case.id,
                        action_type=action_type,
                        status=action_status,
                        idempotency_key=f"recovery_action:{case.id}:{action_type.value}:1",
                        attempt_number=1,
                        provider_reference=f"https://rzp.io/l/demo_{idx:04d}"
                        if action_type == RecoveryActionType.CREATE_PAYMENT_LINK
                        else None,
                        executed_at=utcnow() - timedelta(minutes=30)
                        if action_status == RecoveryActionStatus.EXECUTED
                        else None,
                    )
                    session.add(action)

                    decision = AuditEvent(
                        merchant_id=merchant.id,
                        entity_type="recovery_case",
                        entity_id=str(case.id),
                        event_type="recovery_case.decision",
                        actor="policy_agent_worker",
                        payload={
                            "engine_action": action_type.value,
                            "deterministic_action": action_type.value,
                            "agent_action": action_type.value,
                            "agent_source": "llm" if idx % 3 == 0 else "deterministic_fallback",
                            "agent_reason": "Mock LLM selected engine candidate."
                            if idx % 3 == 0
                            else "llm_disabled",
                            "final_action": action_type.value,
                            "final_policy_approved": True,
                            "final_policy_reason": "policy_approved",
                            "final_status": status.value,
                        },
                    )
                    session.add(decision)

            session.flush()
            merchant_id = merchant.id

    print("Seeded Demo Merchant with 35 recovery cases.")
    print(f"merchant_id={merchant_id}")


if __name__ == "__main__":
    main()