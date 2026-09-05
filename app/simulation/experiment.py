import random
from dataclasses import dataclass, field

from app.models.enums import RecoveryActionType
from app.simulation.baseline import baseline_decide
from app.simulation.outcomes import (
    get_contact_count,
    get_time_to_recovery_hours,
    simulate_outcome,
)
from app.simulation.population import SimulatedPayment
from app.simulation.recoverai import recoverai_decide


@dataclass
class StrategyResult:
    strategy_name: str
    total_cases: int = 0
    recovered_cases: int = 0
    total_amount_at_risk_minor: int = 0
    recovered_amount_minor: int = 0
    total_contacts: int = 0
    total_time_to_recovery_hours: float = 0.0
    action_counts: dict[str, int] = field(default_factory=dict)

    @property
    def recovery_rate(self) -> float:
        if self.total_cases == 0:
            return 0.0
        return self.recovered_cases / self.total_cases

    @property
    def avg_time_to_recovery_hours(self) -> float:
        if self.recovered_cases == 0:
            return 0.0
        return self.total_time_to_recovery_hours / self.recovered_cases

    @property
    def contacts_per_case(self) -> float:
        if self.total_cases == 0:
            return 0.0
        return self.total_contacts / self.total_cases


def run_experiment(
    population: list[SimulatedPayment],
    seed: int = 42,
) -> tuple[StrategyResult, StrategyResult]:
    rng_baseline = random.Random(seed)
    rng_recoverai = random.Random(seed)

    baseline_result = StrategyResult(strategy_name="Baseline")
    recoverai_result = StrategyResult(strategy_name="RecoverAI")

    for payment in population:
        # Baseline
        baseline_action = baseline_decide(payment)
        baseline_action_value = baseline_action.value

        baseline_result.total_cases += 1
        baseline_result.total_amount_at_risk_minor += payment.amount_minor
        baseline_result.action_counts[baseline_action_value] = (
            baseline_result.action_counts.get(baseline_action_value, 0) + 1
        )

        baseline_recovered = simulate_outcome(
            payment.failure_category, baseline_action_value, rng_baseline
        )
        baseline_result.total_contacts += get_contact_count(baseline_action_value)

        if baseline_recovered:
            baseline_result.recovered_cases += 1
            baseline_result.recovered_amount_minor += payment.amount_minor
            baseline_result.total_time_to_recovery_hours += get_time_to_recovery_hours(
                baseline_action_value
            )

        # RecoverAI
        recoverai_action = recoverai_decide(payment)
        recoverai_action_value = recoverai_action.value

        recoverai_result.total_cases += 1
        recoverai_result.total_amount_at_risk_minor += payment.amount_minor
        recoverai_result.action_counts[recoverai_action_value] = (
            recoverai_result.action_counts.get(recoverai_action_value, 0) + 1
        )

        recoverai_recovered = simulate_outcome(
            payment.failure_category, recoverai_action_value, rng_recoverai
        )
        recoverai_result.total_contacts += get_contact_count(recoverai_action_value)

        if recoverai_recovered:
            recoverai_result.recovered_cases += 1
            recoverai_result.recovered_amount_minor += payment.amount_minor
            recoverai_result.total_time_to_recovery_hours += get_time_to_recovery_hours(
                recoverai_action_value
            )

    return baseline_result, recoverai_result


def calculate_incremental_recovered_revenue(
    baseline: StrategyResult,
    recoverai: StrategyResult,
) -> int:
    return recoverai.recovered_amount_minor - baseline.recovered_amount_minor