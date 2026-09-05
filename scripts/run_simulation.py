import argparse
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.simulation.experiment import (
    calculate_incremental_recovered_revenue,
    run_experiment,
)
from app.simulation.population import generate_population


def format_inr(amount_minor: int) -> str:
    """Format paise as INR string."""
    rupees = amount_minor / 100
    return f"₹{rupees:,.2f}"


def print_results(baseline, recoverai, incremental, population_size, seed):
    print()
    print("╔" + "═" * 62 + "╗")
    print("║" + "  SIMULATED BENCHMARK — NOT PRODUCTION DATA".center(62) + "║")
    print("╠" + "═" * 62 + "╣")
    print(f"║  Population: {population_size:,} synthetic failed payments".ljust(63) + "║")
    print(f"║  Seed: {seed}".ljust(63) + "║")
    print("╠" + "═" * 22 + "╦" + "═" * 18 + "╦" + "═" * 20 + "╣")
    print("║  Metric".ljust(23) + "║  Baseline".ljust(19) + "║  RecoverAI".ljust(21) + "║")
    print("╠" + "═" * 22 + "╬" + "═" * 18 + "╬" + "═" * 20 + "╣")

    rows = [
        ("Recovery Rate", f"{baseline.recovery_rate:.1%}", f"{recoverai.recovery_rate:.1%}"),
        ("Recovered Cases", f"{baseline.recovered_cases:,}", f"{recoverai.recovered_cases:,}"),
        ("₹ Recovered", format_inr(baseline.recovered_amount_minor), format_inr(recoverai.recovered_amount_minor)),
        ("₹ At Risk", format_inr(baseline.total_amount_at_risk_minor), format_inr(recoverai.total_amount_at_risk_minor)),
        ("Contacts", f"{baseline.total_contacts:,}", f"{recoverai.total_contacts:,}"),
        ("Contacts/Case", f"{baseline.contacts_per_case:.2f}", f"{recoverai.contacts_per_case:.2f}"),
        ("Avg Time (hrs)", f"{baseline.avg_time_to_recovery_hours:.1f}", f"{recoverai.avg_time_to_recovery_hours:.1f}"),
    ]

    for label, b_val, r_val in rows:
        print(f"║  {label}".ljust(23) + f"║  {b_val}".ljust(19) + f"║  {r_val}".ljust(21) + "║")

    print("╚" + "═" * 22 + "╩" + "═" * 18 + "╩" + "═" * 20 + "╝")
    print()
    print(f"  Incremental Recovered Revenue: {format_inr(incremental)}")
    print()

    print("  Action Distribution:")
    print(f"    {'Action':<25} {'Baseline':>10} {'RecoverAI':>10}")
    print(f"    {'-'*25} {'-'*10} {'-'*10}")

    all_actions = set(baseline.action_counts.keys()) | set(recoverai.action_counts.keys())
    for action in sorted(all_actions):
        b_count = baseline.action_counts.get(action, 0)
        r_count = recoverai.action_counts.get(action, 0)
        print(f"    {action:<25} {b_count:>10,} {r_count:>10,}")

    print()
    print("  ⚠ All results are SIMULATED BENCHMARK.")
    print("  ⚠ Do not present these as production recovery rates.")
    print()


def main():
    parser = argparse.ArgumentParser(description="Run RecoverAI simulated business experiment")
    parser.add_argument("--size", type=int, default=10_000, help="Number of synthetic failed payments (default: 10000)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility (default: 42)")

    args = parser.parse_args()

    print(f"\nGenerating {args.size:,} synthetic failed payments (seed={args.seed})...")
    population = generate_population(size=args.size, seed=args.seed)

    print("Running experiment...")
    baseline, recoverai = run_experiment(population, seed=args.seed)
    incremental = calculate_incremental_recovered_revenue(baseline, recoverai)

    print_results(baseline, recoverai, incremental, args.size, args.seed)

    # --- JSON SAVE BLOCK (GUARANTEED ABSOLUTE PATH) ---
    project_root = Path(__file__).resolve().parents[1]
    output_path = project_root / "simulation_results.json"

    results_for_dashboard = {
        "baseline": {
            "total_cases": baseline.total_cases,
            "recovered_cases": baseline.recovered_cases,
            "recovery_rate": baseline.recovery_rate,
            "total_amount_at_risk_minor": baseline.total_amount_at_risk_minor,
            "recovered_amount_minor": baseline.recovered_amount_minor,
            "total_contacts": baseline.total_contacts,
            "avg_time_to_recovery_hours": baseline.avg_time_to_recovery_hours,
            "action_counts": baseline.action_counts,
        },
        "recoverai": {
            "total_cases": recoverai.total_cases,
            "recovered_cases": recoverai.recovered_cases,
            "recovery_rate": recoverai.recovery_rate,
            "total_amount_at_risk_minor": recoverai.total_amount_at_risk_minor,
            "recovered_amount_minor": recoverai.recovered_amount_minor,
            "total_contacts": recoverai.total_contacts,
            "avg_time_to_recovery_hours": recoverai.avg_time_to_recovery_hours,
            "action_counts": recoverai.action_counts,
        },
        "incremental_recovered_revenue_minor": incremental,
        "population_size": args.size,
        "seed": args.seed,
    }

    with open(output_path, "w") as f:
        json.dump(results_for_dashboard, f, indent=2)

    print(f"  Results saved to {output_path}")


if __name__ == "__main__":
    main()