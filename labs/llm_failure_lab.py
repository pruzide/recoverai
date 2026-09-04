import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.agents.recovery_agent import run_recovery_agent
from app.agents.schemas import AgentDecisionRequest
from app.config import settings
from app.models.enums import RecoveryActionType


def make_request():
    return AgentDecisionRequest(
        merchant_id="00000000-0000-0000-0000-000000000000",
        recovery_case_id="11111111-1111-1111-1111-111111111111",
        amount_minor=5_000,
        currency="INR",
        failure_category="expired_instrument",
        engine_candidate_action=RecoveryActionType.CREATE_PAYMENT_LINK,
        deterministic_final_action=RecoveryActionType.STOP,
        total_action_count=0,
        reminder_count=0,
        active_payment_link_count=0,
    )


def run_mode(mode: str):
    settings.llm_enabled = True
    settings.llm_provider = "mock"
    settings.llm_mock_mode = mode

    decision = run_recovery_agent(make_request())

    print(f"mode={mode}")
    print("  source:", decision.source)
    print("  action:", decision.selected_action.value)
    print("  reason:", decision.reason)
    print()

    return decision


def main():
    normal = run_mode("normal")
    timeout = run_mode("timeout")
    malformed = run_mode("malformed")
    illegal = run_mode("illegal_action")

    assert normal.source == "llm"
    assert normal.selected_action == RecoveryActionType.CREATE_PAYMENT_LINK

    assert timeout.source == "deterministic_fallback"
    assert timeout.selected_action == RecoveryActionType.STOP

    assert malformed.source == "deterministic_fallback"
    assert malformed.selected_action == RecoveryActionType.STOP

    assert illegal.source == "deterministic_fallback"
    assert illegal.selected_action == RecoveryActionType.STOP

    print("LAB PASSED: LLM failures safely fall back to deterministic recovery.")


if __name__ == "__main__":
    main()