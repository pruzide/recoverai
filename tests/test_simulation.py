from app.models.enums import RecoveryActionType
from app.simulation.baseline import baseline_decide
from app.simulation.experiment import (
    calculate_incremental_recovered_revenue,
    run_experiment,
)
from app.simulation.population import SimulatedPayment, generate_population
from app.simulation.recoverai import recoverai_decide


def test_population_is_deterministic_with_seed():
    pop1 = generate_population(size=100, seed=42)
    pop2 = generate_population(size=100, seed=42)
    assert len(pop1) == 100
    assert len(pop2) == 100
    for p1, p2 in zip(pop1, pop2):
        assert p1.payment_id == p2.payment_id
        assert p1.amount_minor == p2.amount_minor
        assert p1.failure_category == p2.failure_category


def test_population_different_seed_different_data():
    pop1 = generate_population(size=10, seed=42)
    pop2 = generate_population(size=10, seed=99)
    ids1 = [p.payment_id for p in pop1]
    ids2 = [p.payment_id for p in pop2]
    assert ids1 != ids2


def test_baseline_always_sends_reminder():
    payment = SimulatedPayment(
        payment_id="pay_test",
        merchant_id="merchant_test",
        amount_minor=500_000,
        currency="INR",
        failure_category="expired_instrument",
    )
    action = baseline_decide(payment)
    assert action == RecoveryActionType.SEND_REMINDER


def test_recoverai_uses_engine_and_policy():
    # 400_000 paise = ₹4,000 — below the 500_000 high-value threshold
    payment = SimulatedPayment(
        payment_id="pay_test",
        merchant_id="merchant_test",
        amount_minor=400_000,
        currency="INR",
        failure_category="expired_instrument",
    )
    action = recoverai_decide(payment)
    assert action == RecoveryActionType.CREATE_PAYMENT_LINK


def test_recoverai_stops_low_value():
    payment = SimulatedPayment(
        payment_id="pay_test",
        merchant_id="merchant_test",
        amount_minor=500,
        currency="INR",
        failure_category="expired_instrument",
    )
    action = recoverai_decide(payment)
    assert action == RecoveryActionType.STOP


def test_recoverai_escalates_high_value():
    # 6_000_000 paise = ₹60,000 — above the 5_000_000 high-value threshold
    payment = SimulatedPayment(
        payment_id="pay_test",
        merchant_id="merchant_test",
        amount_minor=6_000_000,
        currency="INR",
        failure_category="expired_instrument",
    )
    action = recoverai_decide(payment)
    assert action == RecoveryActionType.ESCALATE


def test_experiment_produces_valid_metrics():
    population = generate_population(size=100, seed=42)
    baseline, recoverai = run_experiment(population, seed=42)

    assert baseline.total_cases == 100
    assert recoverai.total_cases == 100
    assert 0 <= baseline.recovery_rate <= 1.0
    assert 0 <= recoverai.recovery_rate <= 1.0
    assert baseline.recovered_cases <= baseline.total_cases
    assert recoverai.recovered_cases <= recoverai.total_cases

    incremental = calculate_incremental_recovered_revenue(baseline, recoverai)
    assert isinstance(incremental, int)


def test_experiment_is_reproducible():
    population = generate_population(size=50, seed=42)
    baseline1, recoverai1 = run_experiment(population, seed=42)
    baseline2, recoverai2 = run_experiment(population, seed=42)

    assert baseline1.recovered_cases == baseline2.recovered_cases
    assert recoverai1.recovered_cases == recoverai2.recovered_cases
    assert baseline1.recovered_amount_minor == baseline2.recovered_amount_minor
    assert recoverai1.recovered_amount_minor == recoverai2.recovered_amount_minor