from dataclasses import dataclass
from typing import Optional

from app.domain.recovery_state import is_terminal
from app.models.enums import RecoveryActionType, RecoveryCaseStatus


@dataclass(frozen=True)
class PolicyLimits:
    max_actions_per_case: int
    max_reminders_per_case: int
    one_active_payment_link: bool
    high_value_escalation_enabled: bool
    high_value_threshold_minor: int


@dataclass(frozen=True)
class PolicyInput:
    case_status: RecoveryCaseStatus
    amount_minor: int
    candidate_action: RecoveryActionType
    total_action_count: int
    reminder_count: int
    active_payment_link_count: int


@dataclass(frozen=True)
class PolicyDecision:
    approved: bool
    final_action: RecoveryActionType
    reason: str
    delay_hours: Optional[float] = None


def evaluate_policy(
    limits: PolicyLimits,
    policy_input: PolicyInput,
    candidate_delay_hours: Optional[float] = None,
) -> PolicyDecision:
    if is_terminal(policy_input.case_status):
        return PolicyDecision(
            approved=False,
            final_action=RecoveryActionType.STOP,
            reason="terminal_state_protected",
        )

    candidate = policy_input.candidate_action

    if (
        limits.high_value_escalation_enabled
        and policy_input.amount_minor >= limits.high_value_threshold_minor
    ):
        if candidate not in (
            RecoveryActionType.ESCALATE,
            RecoveryActionType.STOP,
        ):
            return PolicyDecision(
                approved=False,
                final_action=RecoveryActionType.ESCALATE,
                reason="high_value_requires_escalation",
            )

    if policy_input.total_action_count >= limits.max_actions_per_case:
        return PolicyDecision(
            approved=False,
            final_action=RecoveryActionType.STOP,
            reason="max_actions_per_case_reached",
        )

    if (
        candidate == RecoveryActionType.SEND_REMINDER
        and policy_input.reminder_count >= limits.max_reminders_per_case
    ):
        return PolicyDecision(
            approved=False,
            final_action=RecoveryActionType.STOP,
            reason="max_reminders_reached",
        )

    if (
        candidate == RecoveryActionType.CREATE_PAYMENT_LINK
        and limits.one_active_payment_link
        and policy_input.active_payment_link_count > 0
    ):
        return PolicyDecision(
            approved=False,
            final_action=RecoveryActionType.WAIT,
            reason="active_payment_link_exists",
            delay_hours=1.0,
        )

    if candidate == RecoveryActionType.WAIT:
        return PolicyDecision(
            approved=True,
            final_action=RecoveryActionType.WAIT,
            reason="policy_approved_wait",
            delay_hours=candidate_delay_hours,
        )

    return PolicyDecision(
        approved=True,
        final_action=candidate,
        reason="policy_approved",
    )
