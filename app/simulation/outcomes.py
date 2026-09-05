import random

SIMULATED_RECOVERY_PROBABILITIES: dict[str, dict[str, float]] = {
    "expired_instrument": {
        "CREATE_PAYMENT_LINK": 0.45,
        "SEND_REMINDER": 0.25,
        "WAIT": 0.15,
        "ESCALATE": 0.50,
        "STOP": 0.00,
    },
    "insufficient_funds": {
        "WAIT": 0.35,
        "SEND_REMINDER": 0.20,
        "CREATE_PAYMENT_LINK": 0.15,
        "ESCALATE": 0.45,
        "STOP": 0.00,
    },
    "temporary_network": {
        "SEND_REMINDER": 0.40,
        "WAIT": 0.30,
        "CREATE_PAYMENT_LINK": 0.20,
        "ESCALATE": 0.40,
        "STOP": 0.00,
    },
    "issuer_failure": {
        "ESCALATE": 0.55,
        "WAIT": 0.10,
        "SEND_REMINDER": 0.05,
        "CREATE_PAYMENT_LINK": 0.05,
        "STOP": 0.00,
    },
    "unknown": {
        "WAIT": 0.10,
        "SEND_REMINDER": 0.08,
        "CREATE_PAYMENT_LINK": 0.05,
        "ESCALATE": 0.35,
        "STOP": 0.00,
    },
}

SIMULATED_TIME_TO_RECOVERY_HOURS: dict[str, float] = {
    "SEND_REMINDER": 1.0,
    "CREATE_PAYMENT_LINK": 2.0,
    "WAIT": 24.0,
    "ESCALATE": 48.0,
    "STOP": 0.0,
}

SIMULATED_CONTACT_COUNT: dict[str, int] = {
    "SEND_REMINDER": 1,
    "CREATE_PAYMENT_LINK": 1,
    "WAIT": 0,
    "ESCALATE": 0,
    "STOP": 0,
}


def get_recovery_probability(failure_category: str, action_type: str) -> float:
    category_probs = SIMULATED_RECOVERY_PROBABILITIES.get(failure_category)
    if category_probs is None:
        return 0.0
    return category_probs.get(action_type, 0.0)


def simulate_outcome(failure_category: str, action_type: str, rng: random.Random) -> bool:
    probability = get_recovery_probability(failure_category, action_type)
    return rng.random() < probability


def get_time_to_recovery_hours(action_type: str) -> float:
    return SIMULATED_TIME_TO_RECOVERY_HOURS.get(action_type, 0.0)


def get_contact_count(action_type: str) -> int:
    return SIMULATED_CONTACT_COUNT.get(action_type, 0)