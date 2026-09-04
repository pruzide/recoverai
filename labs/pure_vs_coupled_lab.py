import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.domain.recovery_engine import evaluate_recovery


def simulate_coupled_task(amount, category):
    """
    Simulates a naive task that mixes DB, network, and business logic.
    """

    time.sleep(0.001)

    if amount < 1000:
        action = "STOP"
    elif category == "expired_instrument":
        time.sleep(0.005)
        action = "CREATE_PAYMENT_LINK"
    else:
        action = "SEND_REMINDER"

    time.sleep(0.001)

    return action


def main():
    test_cases = [
        (500, "expired_instrument"),
        (5000, "expired_instrument"),
        (5000, "insufficient_funds"),
        (5000, "temporary_network"),
    ] * 2500

    print("=== Coupled Task Simulation ===")

    start = time.perf_counter()

    for amount, category in test_cases:
        simulate_coupled_task(amount, category)

    coupled_time = time.perf_counter() - start

    print(f"Processed 10,000 cases in {coupled_time:.2f} seconds")

    print()
    print("=== Pure Domain Engine Simulation ===")

    start = time.perf_counter()

    for amount, category in test_cases:
        evaluate_recovery(amount, category)

    pure_time = time.perf_counter() - start

    print(f"Processed 10,000 cases in {pure_time:.4f} seconds")

    print()
    print(f"Pure engine is roughly {coupled_time / pure_time:.0f}x faster.")
    print("Lesson: keep business rules pure and testable.")


if __name__ == "__main__":
    main()