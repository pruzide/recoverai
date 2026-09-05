import hashlib
import hmac
import json
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    Merchant,
    Payment,
    RecoveryCase,
)
from app.models.enums import (
    PaymentStatus,
    RecoveryCaseStatus,
)


SECRET = "test_webhook_secret"


def sign(body: bytes) -> str:
    return hmac.new(
        SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()


def test_captured_webhook_with_notes_recovers_case(db_session):
    merchant = Merchant(name="Notes Merchant")
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
        status=RecoveryCaseStatus.WAITING,
        amount_minor=payment.amount_minor,
        currency=payment.currency,
        version=5,
    )
    db_session.add(case)
    db_session.commit()

    payload = {
        "id": f"evt_{uuid.uuid4().hex}",
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_{uuid.uuid4().hex}",
                    "amount": 5_000,
                    "currency": "INR",
                    "status": "captured",
                    "notes": {
                        "recoverai_merchant_id": str(merchant.id),
                        "recoverai_recovery_case_id": str(case.id),
                    },
                }
            }
        },
    }

    body = json.dumps(payload).encode("utf-8")

    with TestClient(app) as client:
        response = client.post(
            f"/webhooks/razorpay/{merchant.id}",
            content=body,
            headers={
                "X-Razorpay-Signature": sign(body),
                "Content-Type": "application/json",
            },
        )

    assert response.status_code == 200

    db_session.expire_all()

    refreshed_case = db_session.get(RecoveryCase, case.id)

    assert refreshed_case.status == RecoveryCaseStatus.RECOVERED