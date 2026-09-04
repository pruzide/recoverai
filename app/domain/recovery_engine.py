from dataclasses import dataclass
from typing import Optional

from app.models.enums import RecoveryActionType


@dataclass(frozen=True)
class RecoveryDecision:
    action: RecoveryActionType
    reason: str
    delay_hours: Optional[float] = None


MIN_RECOVERABLE_AMOUNT_MINOR = 1000


def evaluate_recovery(
    amount_minor: int,
    failure_category: Optional[str],
) -> RecoveryDecision:
    """
    Deterministic recovery strategy engine.

    This function contains NO database calls, NO network calls,
    and NO LLM calls. It is a pure business rule evaluator.
    """

    if amount_minor < MIN_RECOVERABLE_AMOUNT_MINOR:
        return RecoveryDecision(
            action=RecoveryActionType.STOP,
            reason="low_value_not_worth_recovery",
        )

    category = (failure_category or "unknown").strip().lower()

    if category == "expired_instrument":
        return RecoveryDecision(
            action=RecoveryActionType.CREATE_PAYMENT_LINK,
            reason="expired_instrument_requires_new_link",
        )

    if category == "insufficient_funds":
        return RecoveryDecision(
            action=RecoveryActionType.WAIT,
            reason="insufficient_funds_wait_for_funds",
            delay_hours=24.0,
        )

    if category == "temporary_network":
        return RecoveryDecision(
            action=RecoveryActionType.SEND_REMINDER,
            reason="temporary_network_send_reminder",
        )

    if category == "issuer_failure":
        return RecoveryDecision(
            action=RecoveryActionType.ESCALATE,
            reason="issuer_failure_requires_manual_review",
        )

    return RecoveryDecision(
        action=RecoveryActionType.STOP,
        reason="unknown_or_unrecoverable_failure",
    )