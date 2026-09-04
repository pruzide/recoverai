import sys
import uuid
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db import get_session_factory
from app.models import Merchant, OutboxEvent, Payment
from app.models.enums import OutboxEventStatus, PaymentStatus


SessionLocal = get_session_factory()


def publish_to_queue(payment_id):
    raise RuntimeError("Simulated crash or queue failure before publish")


def main():
    # 1. Create lab merchant (Fresh Session)
    with SessionLocal() as session:
        with session.begin():
            merchant = Merchant(name="Dual Write Lab Merchant")
            session.add(merchant)
            session.flush()
            merchant_id = merchant.id

    print("=== Naive dual-write pattern ===")

    naive_payment_reference = f"pay_naive_{uuid.uuid4().hex}"

    # 2. Naive Payment (Fresh Session)
    with SessionLocal() as session:
        with session.begin():
            payment = Payment(
                merchant_id=merchant_id,
                provider="razorpay",
                provider_payment_id=naive_payment_reference,
                status=PaymentStatus.FAILED,
                amount_minor=1000,
                currency="INR",
            )

            session.add(payment)
            session.flush()

            naive_payment_id = payment.id

        print("Database commit succeeded.")

        try:
            publish_to_queue(naive_payment_id)
        except RuntimeError as exc:
            print("Queue publish failed:", exc)

        outbox_count = session.execute(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == str(naive_payment_id)
            )
        ).scalars().all()

        print("Outbox rows for naive payment:", len(outbox_count))
        print("Result: business work can be lost.\n")

    print("=== Transactional outbox pattern ===")

    safe_payment_reference = f"pay_outbox_{uuid.uuid4().hex}"

    # 3. Transactional Outbox Payment (Fresh Session)
    with SessionLocal() as session:
        with session.begin():
            payment = Payment(
                merchant_id=merchant_id,
                provider="razorpay",
                provider_payment_id=safe_payment_reference,
                status=PaymentStatus.FAILED,
                amount_minor=2000,
                currency="INR",
            )

            session.add(payment)
            session.flush()

            outbox = OutboxEvent(
                merchant_id=merchant_id,
                aggregate_type="payment",
                aggregate_id=str(payment.id),
                event_type="payment.failed",
                payload={
                    "provider_payment_id": payment.provider_payment_id,
                    "amount_minor": payment.amount_minor,
                    "currency": payment.currency,
                },
                idempotency_key=f"payment.failed:{payment.id}",
                status=OutboxEventStatus.PENDING,
            )

            session.add(outbox)

        print("Database commit succeeded with outbox row.")

        try:
            publish_to_queue(payment.id)
        except RuntimeError as exc:
            print("Queue publish failed:", exc)

        outbox_rows = session.execute(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == str(payment.id)
            )
        ).scalars().all()

        print("Outbox rows for safe payment:", len(outbox_rows))
        print("Result: work remains durable and can be retried.\n")

    # 4. Cleanup (Fresh Session)
    with SessionLocal() as session:
        with session.begin():
            outbox_to_delete = session.execute(
                select(OutboxEvent).where(
                    OutboxEvent.merchant_id == merchant_id
                )
            ).scalars().all()
            for row in outbox_to_delete:
                session.delete(row)

            payments_to_delete = session.execute(
                select(Payment).where(
                    Payment.merchant_id == merchant_id
                )
            ).scalars().all()
            for row in payments_to_delete:
                session.delete(row)

            merchant_row = session.get(Merchant, merchant_id)
            if merchant_row:
                session.delete(merchant_row)

    print("Lab cleanup complete.")


if __name__ == "__main__":
    main()