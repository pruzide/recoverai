from app.domain.recovery_engine import evaluate_recovery
from app.models.enums import RecoveryActionType


def test_low_value_stops():
    decision = evaluate_recovery(500, "expired_instrument")

    assert decision.action == RecoveryActionType.STOP
    assert "low_value" in decision.reason


def test_expired_instrument_creates_link():
    decision = evaluate_recovery(5000, "expired_instrument")

    assert decision.action == RecoveryActionType.CREATE_PAYMENT_LINK


def test_insufficient_funds_waits():
    decision = evaluate_recovery(5000, "insufficient_funds")

    assert decision.action == RecoveryActionType.WAIT
    assert decision.delay_hours == 24.0


def test_temporary_network_reminds():
    decision = evaluate_recovery(5000, "temporary_network")

    assert decision.action == RecoveryActionType.SEND_REMINDER


def test_issuer_failure_escalates():
    decision = evaluate_recovery(5000, "issuer_failure")

    assert decision.action == RecoveryActionType.ESCALATE


def test_unknown_failure_stops():
    decision = evaluate_recovery(5000, None)

    assert decision.action == RecoveryActionType.STOP