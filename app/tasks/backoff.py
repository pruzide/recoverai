import random


def exponential_backoff_with_jitter(
    attempt: int,
    base: float = 2.0,
    cap: float = 60.0,
) -> float:
    attempt = max(0, attempt)

    max_delay = min(cap, base * (2 ** attempt))
    min_delay = max_delay / 2.0

    return round(random.uniform(min_delay, max_delay), 3)
