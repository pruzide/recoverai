from app.agents.recovery_agent import run_recovery_agent
from app.agents.schemas import AgentDecisionRequest
from app.config import settings
from app.models.enums import RecoveryActionType


def make_request(
    engine_action=RecoveryActionType.CREATE_PAYMENT_LINK,
    deterministic_action=RecoveryActionType.STOP,
):
    return AgentDecisionRequest(
        merchant_id="00000000-0000-0000-0000-000000000000",
        recovery_case_id="11111111-1111-1111-1111-111111111111",
        amount_minor=5_000,
        currency="INR",
        failure_category="expired_instrument",
        engine_candidate_action=engine_action,
        deterministic_final_action=deterministic_action,
        total_action_count=0,
        reminder_count=0,
        active_payment_link_count=0,
    )


def test_agent_disabled_uses_fallback(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", False)

    decision = run_recovery_agent(
        make_request(
            engine_action=RecoveryActionType.CREATE_PAYMENT_LINK,
            deterministic_action=RecoveryActionType.STOP,
        )
    )

    assert decision.source == "deterministic_fallback"
    assert decision.selected_action == RecoveryActionType.STOP


def test_mock_llm_normal_selects_engine_candidate(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_mock_mode", "normal")

    decision = run_recovery_agent(
        make_request(
            engine_action=RecoveryActionType.CREATE_PAYMENT_LINK,
            deterministic_action=RecoveryActionType.STOP,
        )
    )

    assert decision.source == "llm"
    assert decision.selected_action == RecoveryActionType.CREATE_PAYMENT_LINK


def test_mock_llm_timeout_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_mock_mode", "timeout")

    decision = run_recovery_agent(
        make_request(
            engine_action=RecoveryActionType.CREATE_PAYMENT_LINK,
            deterministic_action=RecoveryActionType.STOP,
        )
    )

    assert decision.source == "deterministic_fallback"
    assert decision.selected_action == RecoveryActionType.STOP


def test_mock_llm_malformed_output_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_mock_mode", "malformed")

    decision = run_recovery_agent(
        make_request(
            engine_action=RecoveryActionType.CREATE_PAYMENT_LINK,
            deterministic_action=RecoveryActionType.STOP,
        )
    )

    assert decision.source == "deterministic_fallback"
    assert decision.selected_action == RecoveryActionType.STOP


def test_mock_llm_illegal_action_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_mock_mode", "illegal_action")

    decision = run_recovery_agent(
        make_request(
            engine_action=RecoveryActionType.CREATE_PAYMENT_LINK,
            deterministic_action=RecoveryActionType.STOP,
        )
    )

    assert decision.source == "deterministic_fallback"
    assert decision.selected_action == RecoveryActionType.STOP