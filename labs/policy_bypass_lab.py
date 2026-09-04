import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.domain.policy import PolicyInput, PolicyLimits, evaluate_policy
from app.domain.recovery_engine import evaluate_recovery
from app.models.enums import RecoveryActionType, RecoveryCaseStatus


def main():
    amount_minor = 600_000
    failure_category = "expired_instrument"

    engine_decision = evaluate_recovery(amount_minor, failure_category)

    print("=== Without policy ===")
    print("Engine action:", engine_decision.action.value)
    print("Engine reason:", engine_decision.reason)

    limits = PolicyLimits(
        max_actions_per_case=3,
        max_reminders_per_case=2,
        one_active_payment_link=True,
        high_value_escalation_enabled=True,
        high_value_threshold_minor=500_000,
    )

    policy_input = PolicyInput(
        case_status=RecoveryCaseStatus.ANALYSING,
        amount_minor=amount_minor,
        candidate_action=engine_decision.action,
        total_action_count=0,
        reminder_count=0,
        active_payment_link_count=0,
    )

    policy_decision = evaluate_policy(
        limits=limits,
        policy_input=policy_input,
        candidate_delay_hours=engine_decision.delay_hours,
    )

    print("\n=== With policy ===")
    print("Approved:", policy_decision.approved)
    print("Final action:", policy_decision.final_action.value)
    print("Reason:", policy_decision.reason)

    assert engine_decision.action == RecoveryActionType.CREATE_PAYMENT_LINK
    assert policy_decision.final_action == RecoveryActionType.ESCALATE

    print("\nLAB PASSED: policy prevented high-value automatic payment link creation.")


if __name__ == "__main__":
    main()
