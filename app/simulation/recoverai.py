from app.domain.policy import PolicyInput, PolicyLimits, evaluate_policy
from app.domain.recovery_engine import evaluate_recovery
from app.models.enums import RecoveryActionType, RecoveryCaseStatus
from app.simulation.population import SimulatedPayment


DEFAULT_SIMULATION_POLICY = PolicyLimits(
    max_actions_per_case=3,
    max_reminders_per_case=2,
    one_active_payment_link=True,
    high_value_escalation_enabled=True,
    high_value_threshold_minor=5_000_000,
)


def recoverai_decide(
    payment: SimulatedPayment,
    policy_limits: PolicyLimits | None = None,
) -> RecoveryActionType:
    if policy_limits is None:
        policy_limits = DEFAULT_SIMULATION_POLICY

    engine_decision = evaluate_recovery(
        amount_minor=payment.amount_minor,
        failure_category=payment.failure_category,
    )

    policy_input = PolicyInput(
        case_status=RecoveryCaseStatus.ANALYSING,
        amount_minor=payment.amount_minor,
        candidate_action=engine_decision.action,
        total_action_count=0,
        reminder_count=0,
        active_payment_link_count=0,
    )

    policy_decision = evaluate_policy(
        limits=policy_limits,
        policy_input=policy_input,
        candidate_delay_hours=engine_decision.delay_hours,
    )

    return policy_decision.final_action