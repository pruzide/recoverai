from app.domain.policy import (
    PolicyInput,
    PolicyLimits,
    evaluate_policy,
)
from app.models.enums import RecoveryActionType, RecoveryCaseStatus


def make_limits():
    return PolicyLimits(
        max_actions_per_case=3,
        max_reminders_per_case=2,
        one_active_payment_link=True,
        high_value_escalation_enabled=True,
        high_value_threshold_minor=500_000,
    )


def make_input(
    candidate_action=RecoveryActionType.CREATE_PAYMENT_LINK,
    case_status=RecoveryCaseStatus.ANALYSING,
    amount_minor=5_000,
    total_action_count=0,
    reminder_count=0,
    active_payment_link_count=0,
):
    return PolicyInput(
        case_status=case_status,
        amount_minor=amount_minor,
        candidate_action=candidate_action,
        total_action_count=total_action_count,
        reminder_count=reminder_count,
        active_payment_link_count=active_payment_link_count,
    )


def test_terminal_state_denies_action():
    decision = evaluate_policy(
        make_limits(),
        make_input(
            candidate_action=RecoveryActionType.SEND_REMINDER,
            case_status=RecoveryCaseStatus.RECOVERED,
        ),
    )

    assert decision.approved is False
    assert decision.final_action == RecoveryActionType.STOP
    assert decision.reason == "terminal_state_protected"


def test_high_value_forces_escalation():
    decision = evaluate_policy(
        make_limits(),
        make_input(
            candidate_action=RecoveryActionType.CREATE_PAYMENT_LINK,
            amount_minor=600_000,
        ),
    )

    assert decision.approved is False
    assert decision.final_action == RecoveryActionType.ESCALATE
    assert decision.reason == "high_value_requires_escalation"


def test_max_actions_reached_falls_back_to_stop():
    decision = evaluate_policy(
        make_limits(),
        make_input(
            candidate_action=RecoveryActionType.SEND_REMINDER,
            total_action_count=3,
        ),
    )

    assert decision.approved is False
    assert decision.final_action == RecoveryActionType.STOP
    assert decision.reason == "max_actions_per_case_reached"


def test_max_reminders_reached_falls_back_to_stop():
    decision = evaluate_policy(
        make_limits(),
        make_input(
            candidate_action=RecoveryActionType.SEND_REMINDER,
            reminder_count=2,
        ),
    )

    assert decision.approved is False
    assert decision.final_action == RecoveryActionType.STOP
    assert decision.reason == "max_reminders_reached"


def test_active_payment_link_falls_back_to_wait():
    decision = evaluate_policy(
        make_limits(),
        make_input(
            candidate_action=RecoveryActionType.CREATE_PAYMENT_LINK,
            active_payment_link_count=1,
        ),
    )

    assert decision.approved is False
    assert decision.final_action == RecoveryActionType.WAIT
    assert decision.reason == "active_payment_link_exists"
    assert decision.delay_hours == 1.0


def test_normal_payment_link_approved():
    decision = evaluate_policy(
        make_limits(),
        make_input(
            candidate_action=RecoveryActionType.CREATE_PAYMENT_LINK,
        ),
    )

    assert decision.approved is True
    assert decision.final_action == RecoveryActionType.CREATE_PAYMENT_LINK
    assert decision.reason == "policy_approved"
