import sys
import threading
import uuid
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db import get_session_factory
from app.models import (
    AuditEvent,
    Merchant,
    Payment,
    RecoveryCase,
)
from app.models.enums import PaymentStatus, RecoveryCaseStatus
from app.services.recovery_cases import atomic_transition_recovery_case


def create_lab_case():
    SessionLocal = get_session_factory()

    with SessionLocal() as session:
        with session.begin():
            merchant = Merchant(name="Concurrency Lab Merchant")
            session.add(merchant)
            session.flush()

            payment = Payment(
                merchant_id=merchant.id,
                provider="razorpay",
                provider_payment_id=f"pay_lab_{uuid.uuid4().hex}",
                status=PaymentStatus.FAILED,
                amount_minor=9999,
                currency="INR",
            )
            session.add(payment)
            session.flush()

            case = RecoveryCase(
                merchant_id=merchant.id,
                payment_id=payment.id,
                status=RecoveryCaseStatus.ELIGIBLE,
                amount_minor=payment.amount_minor,
                currency=payment.currency,
                version=1,
            )
            session.add(case)
            session.flush()

            return merchant.id, payment.id, case.id


def worker_transition(case_id, barrier, results, errors):
    SessionLocal = get_session_factory()

    try:
        with SessionLocal() as session:
            with session.begin():
                case = session.get(RecoveryCase, case_id)

                barrier.wait(timeout=5)

                rowcount = atomic_transition_recovery_case(
                    session=session,
                    case_id=case.id,
                    expected_status=case.status,
                    expected_version=case.version,
                    new_status=RecoveryCaseStatus.ANALYSING,
                )

                if rowcount == 1:
                    audit = AuditEvent(
                        merchant_id=case.merchant_id,
                        entity_type="recovery_case",
                        entity_id=str(case.id),
                        event_type="recovery_case.analysis_started",
                        actor="lab_worker",
                        payload={
                            "lab": "concurrent_case_transition",
                        },
                    )
                    session.add(audit)

                results.append(rowcount)

    except Exception as exc:
        errors.append(str(exc))


def cleanup(merchant_id, payment_id, case_id):
    SessionLocal = get_session_factory()

    with SessionLocal() as session:
        with session.begin():
            audits = session.execute(
                select(AuditEvent).where(
                    AuditEvent.entity_id == str(case_id)
                )
            ).scalars().all()

            for audit in audits:
                session.delete(audit)

            case = session.get(RecoveryCase, case_id)
            if case:
                session.delete(case)

            payment = session.get(Payment, payment_id)
            if payment:
                session.delete(payment)

            merchant = session.get(Merchant, merchant_id)
            if merchant:
                session.delete(merchant)


def main():
    merchant_id, payment_id, case_id = create_lab_case()

    print("Created lab case:", case_id)

    barrier = threading.Barrier(2)
    results = []
    errors = []

    t1 = threading.Thread(
        target=worker_transition,
        args=(case_id, barrier, results, errors),
    )

    t2 = threading.Thread(
        target=worker_transition,
        args=(case_id, barrier, results, errors),
    )

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    if errors:
        print("Errors:", errors)

    SessionLocal = get_session_factory()

    with SessionLocal() as session:
        case = session.get(RecoveryCase, case_id)

        audit_rows = session.execute(
            select(AuditEvent).where(
                AuditEvent.entity_id == str(case_id)
            )
        ).scalars().all()

        success_count = sum(1 for rowcount in results if rowcount == 1)
        conflict_count = sum(1 for rowcount in results if rowcount == 0)

        print("Successful transitions:", success_count)
        print("Conflicted transitions:", conflict_count)
        print("Final case status:", case.status.value)
        print("Final case version:", case.version)
        print("Audit events:", len(audit_rows))

        if success_count == 1 and len(audit_rows) == 1:
            print("LAB PASSED: duplicate transition prevented")
        else:
            print("LAB FAILED: duplicate transition may be possible")

    cleanup(merchant_id, payment_id, case_id)

    print("Lab cleanup complete.")


if __name__ == "__main__":
    main()
