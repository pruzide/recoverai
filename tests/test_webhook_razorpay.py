import hashlib
import hmac
import json
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import (
    Merchant,
    OutboxEvent,
    Payment,
    RecoveryCase,
    WebhookEvent,
)
from app.models.enums import (
    OutboxEventStatus,
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


def make_event(event_type: str, payment_id: str, event_id: str):
    status = "failed" if event_type == "payment.failed" else "captured"

    return {
        "id": event_id,
        "event": event_type,
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "amount": 7999,
                    "currency": "INR",
                    "status": status,
                    "error_code": "issuer_unavailable" if event_type == "payment.failed" else None,
                    "error_description": "Simulated failure" if event_type == "payment.failed" else None,
                }
            }
        },
    }


def post_webhook(client, merchant_id, payload, signature=None):
    body = json.dumps(payload).encode("utf-8")

    if signature is None:
        signature = sign(body)

    return client.post(
        f"/webhooks/razorpay/{merchant_id}",
        content=body,
        headers={
            "X-Razorpay-Signature": signature,
            "Content-Type": "application/json",
        },
    )


def create_merchant(db_session):
    merchant = Merchant(name="Webhook Merchant")
    db_session.add(merchant)
    db_session.commit()
    return merchant


def test_valid_payment_failed_creates_eligible_recovery_case(db_session):
    merchant = create_merchant(db_session)

    payload = make_event(
        event_type="payment.failed",
        payment_id="pay_test_failed_1",
        event_id="evt_test_failed_1",
    )

    with TestClient(app) as client:
        response = post_webhook(client, merchant.id, payload)

    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "accepted"
    assert body["outcome"] == "recovery_case_created"

    payment = db_session.execute(
        select(Payment).where(
            Payment.provider_payment_id == "pay_test_failed_1"
        )
    ).scalar_one()

    case = db_session.execute(
        select(RecoveryCase).where(
            RecoveryCase.payment_id == payment.id
        )
    ).scalar_one()

    outbox = db_session.execute(
        select(OutboxEvent).where(
            OutboxEvent.aggregate_id == str(case.id)
        )
    ).scalar_one()

    assert payment.status == PaymentStatus.FAILED
    assert case.status == RecoveryCaseStatus.ELIGIBLE
    assert case.version >= 2
    assert outbox.status == OutboxEventStatus.PENDING


def test_duplicate_webhook_is_safely_ignored(db_session):
    merchant = create_merchant(db_session)

    payload = make_event(
        event_type="payment.failed",
        payment_id="pay_test_duplicate",
        event_id="evt_test_duplicate",
    )

    with TestClient(app) as client:
        first = post_webhook(client, merchant.id, payload)
        second = post_webhook(client, merchant.id, payload)

    assert first.status_code == 200
    assert first.json()["status"] == "accepted"

    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"

    webhooks = db_session.execute(
        select(WebhookEvent).where(
            WebhookEvent.provider_event_id == "evt_test_duplicate"
        )
    ).scalars().all()

    cases = db_session.execute(
        select(RecoveryCase)
    ).scalars().all()

    assert len(webhooks) == 1
    assert len(cases) == 1


def test_invalid_signature_is_rejected(db_session):
    merchant = create_merchant(db_session)

    payload = make_event(
        event_type="payment.failed",
        payment_id="pay_test_bad_signature",
        event_id="evt_test_bad_signature",
    )

    with TestClient(app) as client:
        response = post_webhook(
            client,
            merchant.id,
            payload,
            signature="invalid_signature",
        )

    assert response.status_code == 401

    webhooks = db_session.execute(
        select(WebhookEvent)
    ).scalars().all()

    payments = db_session.execute(
        select(Payment)
    ).scalars().all()

    assert len(webhooks) == 0
    assert len(payments) == 0


def test_payment_captured_after_failed_recovers_case(db_session):
    merchant = create_merchant(db_session)

    failed_payload = make_event(
        event_type="payment.failed",
        payment_id="pay_test_capture_after_failed",
        event_id="evt_test_failed_before_capture",
    )

    captured_payload = make_event(
        event_type="payment.captured",
        payment_id="pay_test_capture_after_failed",
        event_id="evt_test_capture_after_failed",
    )

    with TestClient(app) as client:
        failed_response = post_webhook(client, merchant.id, failed_payload)
        captured_response = post_webhook(client, merchant.id, captured_payload)

    assert failed_response.status_code == 200
    assert captured_response.status_code == 200

    payment = db_session.execute(
        select(Payment).where(
            Payment.provider_payment_id == "pay_test_capture_after_failed"
        )
    ).scalar_one()

    case = db_session.execute(
        select(RecoveryCase).where(
            RecoveryCase.payment_id == payment.id
        )
    ).scalar_one()

    assert payment.status == PaymentStatus.CAPTURED
    assert case.status == RecoveryCaseStatus.RECOVERED

    outbox_events = db_session.execute(
        select(OutboxEvent).where(
            OutboxEvent.aggregate_id == str(case.id)
        )
    ).scalars().all()

    event_types = {event.event_type for event in outbox_events}

    assert "recovery_case.eligible" in event_types
    assert "recovery_case.recovered" in event_types


def test_out_of_order_failed_after_captured_does_not_create_case(db_session):
    merchant = create_merchant(db_session)

    captured_payload = make_event(
        event_type="payment.captured",
        payment_id="pay_test_out_of_order",
        event_id="evt_test_captured_first",
    )

    failed_payload = make_event(
        event_type="payment.failed",
        payment_id="pay_test_out_of_order",
        event_id="evt_test_failed_late",
    )

    with TestClient(app) as client:
        captured_response = post_webhook(client, merchant.id, captured_payload)
        failed_response = post_webhook(client, merchant.id, failed_payload)

    assert captured_response.status_code == 200
    assert failed_response.status_code == 200

    payment = db_session.execute(
        select(Payment).where(
            Payment.provider_payment_id == "pay_test_out_of_order"
        )
    ).scalar_one()

    case = db_session.execute(
        select(RecoveryCase).where(
            RecoveryCase.payment_id == payment.id
        )
    ).scalar_one_or_none()

    assert payment.status == PaymentStatus.CAPTURED
    assert case is None