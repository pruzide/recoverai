from typing import Optional
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.policy import PolicyInput, PolicyLimits
from app.models import MerchantPolicy, RecoveryAction, RecoveryCase
from app.models.enums import RecoveryActionStatus, RecoveryActionType


EXCLUDED_ACTION_COUNT_STATUSES = [
    RecoveryActionStatus.DENIED,
    RecoveryActionStatus.CANCELLED,
]

ACTIVE_PAYMENT_LINK_STATUSES = [
    RecoveryActionStatus.PENDING,
    RecoveryActionStatus.APPROVED,
    RecoveryActionStatus.EXECUTING,
]


def get_or_create_default_policy(
    session: Session,
    merchant_id: uuid.UUID,
) -> MerchantPolicy:
    existing = session.execute(
        select(MerchantPolicy).where(
            MerchantPolicy.merchant_id == merchant_id
        )
    ).scalar_one_or_none()

    if existing:
        return existing

    try:
        with session.begin_nested():
            policy = MerchantPolicy(
                merchant_id=merchant_id,
            )
            session.add(policy)
            session.flush()
            return policy

    except IntegrityError:
        return session.execute(
            select(MerchantPolicy).where(
                MerchantPolicy.merchant_id == merchant_id
            )
        ).scalar_one()


def policy_limits_from(policy: MerchantPolicy) -> PolicyLimits:
    return PolicyLimits(
        max_actions_per_case=policy.max_actions_per_case,
        max_reminders_per_case=policy.max_reminders_per_case,
        one_active_payment_link=policy.one_active_payment_link,
        high_value_escalation_enabled=policy.high_value_escalation_enabled,
        high_value_threshold_minor=policy.high_value_threshold_minor,
    )


def build_policy_input(
    session: Session,
    case: RecoveryCase,
    candidate_action: RecoveryActionType,
    current_status: RecoveryCaseStatus,
    exclude_action_id: Optional[uuid.UUID] = None,
) -> PolicyInput:
    base_filters = [
        RecoveryAction.recovery_case_id == case.id,
        RecoveryAction.status.not_in(EXCLUDED_ACTION_COUNT_STATUSES),
    ]

    if exclude_action_id is not None:
        base_filters.append(RecoveryAction.id != exclude_action_id)

    total_action_count = session.execute(
        select(func.count())
        .select_from(RecoveryAction)
        .where(*base_filters)
    ).scalar_one()

    reminder_filters = base_filters + [
        RecoveryAction.action_type == RecoveryActionType.SEND_REMINDER,
    ]

    reminder_count = session.execute(
        select(func.count())
        .select_from(RecoveryAction)
        .where(*reminder_filters)
    ).scalar_one()

    active_link_filters = [
        RecoveryAction.recovery_case_id == case.id,
        RecoveryAction.action_type == RecoveryActionType.CREATE_PAYMENT_LINK,
        RecoveryAction.status.in_(ACTIVE_PAYMENT_LINK_STATUSES),
    ]

    if exclude_action_id is not None:
        active_link_filters.append(RecoveryAction.id != exclude_action_id)

    active_payment_link_count = session.execute(
        select(func.count())
        .select_from(RecoveryAction)
        .where(*active_link_filters)
    ).scalar_one()

    return PolicyInput(
        case_status=current_status,
        amount_minor=case.amount_minor,
        candidate_action=candidate_action,
        total_action_count=total_action_count,
        reminder_count=reminder_count,
        active_payment_link_count=active_payment_link_count,
    )