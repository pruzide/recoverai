from datetime import datetime
from typing import Optional, Tuple
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import RecoveryAction
from app.models.enums import RecoveryActionStatus, RecoveryActionType


def recovery_action_idempotency_key(
    recovery_case_id: uuid.UUID,
    action_type: RecoveryActionType,
    attempt_number: int,
) -> str:
    return (
        f"recovery_action:{recovery_case_id}:"
        f"{action_type.value}:{attempt_number}"
    )


def create_recovery_action_idempotent(
    session: Session,
    *,
    merchant_id: uuid.UUID,
    recovery_case_id: uuid.UUID,
    action_type: RecoveryActionType,
    idempotency_key: str,
    attempt_number: int = 1,
    scheduled_at: Optional[datetime] = None,
) -> Tuple[RecoveryAction, bool]:
    """
    Create a recovery action idempotently.

    Returns:
        action, created

        created=True  -> this call inserted the action
        created=False -> an equivalent action already existed
    """

    existing = session.execute(
        select(RecoveryAction).where(
            RecoveryAction.idempotency_key == idempotency_key
        )
    ).scalar_one_or_none()

    if existing:
        return existing, False

    try:
        with session.begin_nested():
            action = RecoveryAction(
                merchant_id=merchant_id,
                recovery_case_id=recovery_case_id,
                action_type=action_type,
                status=RecoveryActionStatus.PENDING,
                idempotency_key=idempotency_key,
                attempt_number=attempt_number,
                scheduled_at=scheduled_at,
            )

            session.add(action)
            session.flush()

            return action, True

    except IntegrityError:
        existing = session.execute(
            select(RecoveryAction).where(
                RecoveryAction.idempotency_key == idempotency_key
            )
        ).scalar_one_or_none()

        if existing:
            return existing, False

        existing = session.execute(
            select(RecoveryAction).where(
                RecoveryAction.recovery_case_id == recovery_case_id,
                RecoveryAction.action_type == action_type,
                RecoveryAction.attempt_number == attempt_number,
            )
        ).scalar_one_or_none()

        if existing:
            return existing, False

        raise
