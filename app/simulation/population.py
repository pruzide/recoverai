import random
import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class SimulatedPayment:
    payment_id: str
    merchant_id: str
    amount_minor: int
    currency: str
    failure_category: str


FAILURE_CATEGORY_WEIGHTS = [
    ("expired_instrument", 0.25),
    ("insufficient_funds", 0.30),
    ("temporary_network", 0.20),
    ("issuer_failure", 0.15),
    ("unknown", 0.10),
]

FAILURE_CATEGORIES = [c for c, _ in FAILURE_CATEGORY_WEIGHTS]
CATEGORY_WEIGHTS = [w for _, w in FAILURE_CATEGORY_WEIGHTS]

_HEX_CHARS = "0123456789abcdef"


def _random_hex_id(rng: random.Random, length: int = 12) -> str:
    return "".join(rng.choice(_HEX_CHARS) for _ in range(length))


def _random_amount_minor(rng: random.Random) -> int:
    bucket = rng.random()
    if bucket < 0.70:
        return rng.randint(10_000, 500_000)
    elif bucket < 0.90:
        return rng.randint(500_000, 2_000_000)
    elif bucket < 0.98:
        return rng.randint(2_000_000, 10_000_000)
    else:
        return rng.randint(10_000_000, 50_000_000)


def generate_population(
    size: int,
    seed: int = 42,
    merchant_id: str | None = None,
) -> list[SimulatedPayment]:
    rng = random.Random(seed)
    if merchant_id is None:
        merchant_id = f"merchant_sim_{_random_hex_id(rng, 12)}"

    population = []
    for _ in range(size):
        category = rng.choices(
            FAILURE_CATEGORIES,
            weights=CATEGORY_WEIGHTS,
            k=1,
        )[0]

        payment = SimulatedPayment(
            payment_id=f"pay_sim_{_random_hex_id(rng, 12)}",
            merchant_id=merchant_id,
            amount_minor=_random_amount_minor(rng),
            currency="INR",
            failure_category=category,
        )
        population.append(payment)

    return population