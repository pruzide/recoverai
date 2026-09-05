import uuid

from fastapi.testclient import TestClient

from app.main import app
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


def setup_merchant_and_cases(db_session, count=5):
    merchant = Merchant(name="Dashboard Merchant")
    db_session.add(merchant)
    db_session.flush()

    cases = []
    for i in range(count):
        payment = Payment(
            merchant_id=merchant.id,
            provider="razorpay",
            provider_payment_id=f"pay_dash_{uuid.uuid4().hex}",
            status=PaymentStatus.FAILED,
            amount_minor=1000 * (i + 1),
            currency="INR",
        )
        db_session.add(payment)
        db_session.flush()

        status = (
            RecoveryCaseStatus.RECOVERED
            if i % 2 == 0
            else RecoveryCaseStatus.WAITING
        )

        case = RecoveryCase(
            merchant_id=merchant.id,
            payment_id=payment.id,
            status=status,
            amount_minor=payment.amount_minor,
            currency="INR",
            failure_category="expired_instrument",
        )
        db_session.add(case)
        db_session.flush()
        cases.append(case)

        audit = AuditEvent(
            merchant_id=merchant.id,
            entity_type="recovery_case",
            entity_id=str(case.id),
            event_type="recovery_case.decision",
            actor="policy_agent_worker",
            payload={"agent_source": "llm", "reason": "test_reason"},
        )
        db_session.add(audit)

    db_session.commit()
    return merchant, cases


def test_metrics_aggregation(db_session):
    merchant, cases = setup_merchant_and_cases(db_session, count=4)

    with TestClient(app) as client:
        response = client.get(f"/dashboard/metrics/{merchant.id}")

    assert response.status_code == 200
    data = response.json()

    assert data["total_cases"] == 4
    assert data["recovered_cases"] == 2
    assert data["total_amount_at_risk_minor"] == 1000 + 2000 + 3000 + 4000
    assert data["recovered_amount_minor"] == 1000 + 3000
    assert data["recovery_rate_percent"] == 50.0


def test_cases_pagination(db_session):
    merchant, cases = setup_merchant_and_cases(db_session, count=15)

    with TestClient(app) as client:
        response = client.get(
            f"/dashboard/cases?merchant_id={merchant.id}&limit=10&offset=0"
        )

    assert response.status_code == 200
    data = response.json()

    assert data["total_count"] == 15
    assert len(data["items"]) == 10
    assert data["limit"] == 10
    assert data["offset"] == 0

    response2 = client.get(
        f"/dashboard/cases?merchant_id={merchant.id}&limit=10&offset=10"
    )
    data2 = response2.json()
    assert len(data2["items"]) == 5


def test_cases_limit_enforced(db_session):
    merchant, _ = setup_merchant_and_cases(db_session, count=2)

    with TestClient(app) as client:
        response = client.get(
            f"/dashboard/cases?merchant_id={merchant.id}&limit=500"
        )

    assert response.status_code == 422


def test_case_detail_explainability(db_session):
    merchant, cases = setup_merchant_and_cases(db_session, count=1)
    case = cases[0]

    with TestClient(app) as client:
        response = client.get(
            f"/dashboard/cases/{case.id}?merchant_id={merchant.id}"
        )

    assert response.status_code == 200
    data = response.json()

    assert data["case"]["id"] == str(case.id)
    assert len(data["audit_trail"]) == 1
    assert data["audit_trail"][0]["payload"]["agent_source"] == "llm"
    assert data["audit_trail"][0]["payload"]["reason"] == "test_reason"