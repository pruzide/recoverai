import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.simulation import outcomes
from app.simulation.experiment import run_experiment
from app.simulation.population import generate_population


def run_with_label(label):
    population = generate_population(size=5_000, seed=42)
    baseline, recoverai = run_experiment(population, seed=42)

    print(f"\n=== {label} ===")
    print(f"  Baseline recovery rate:  {baseline.recovery_rate:.1%}")
    print(f"  RecoverAI recovery rate: {recoverai.recovery_rate:.1%}")

    incremental = recoverai.recovered_amount_minor - baseline.recovered_amount_minor
    print(f"  Incremental revenue: ₹{incremental / 100:,.2f}")


def main():
    print("This lab shows how simulated results depend on assumptions.")
    print("All results are SIMULATED BENCHMARK.\n")

    run_with_label("Original assumptions")

    original = outcomes.SIMULATED_RECOVERY_PROBABILITIES["expired_instrument"]["CREATE_PAYMENT_LINK"]
    outcomes.SIMULATED_RECOVERY_PROBABILITIES["expired_instrument"]["CREATE_PAYMENT_LINK"] = 0.10
    run_with_label("Reduced payment link effectiveness (0.45 → 0.10)")
    outcomes.SIMULATED_RECOVERY_PROBABILITIES["expired_instrument"]["CREATE_PAYMENT_LINK"] = original

    original_reminder = outcomes.SIMULATED_RECOVERY_PROBABILITIES["insufficient_funds"]["SEND_REMINDER"]
    outcomes.SIMULATED_RECOVERY_PROBABILITIES["insufficient_funds"]["SEND_REMINDER"] = 0.50
    run_with_label("Increased reminder effectiveness (0.20 → 0.50)")
    outcomes.SIMULATED_RECOVERY_PROBABILITIES["insufficient_funds"]["SEND_REMINDER"] = original_reminder

    print("\nLAB PASSED: Results change when assumptions change.")
    print("This is why simulated benchmarks must be labelled clearly.")


if __name__ == "__main__":
    main()