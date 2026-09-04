from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.domain.recovery_state import validate_transition
from app.models import RecoveryCase
from app.models.enums import RecoveryCaseStatus


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def atomic_transition_recovery_case(
    session: Session,
    case_id: UUID,
    expected_status: RecoveryCaseStatus,
    expected_version: int,
    new_status: RecoveryCaseStatus,
) -> int:
    """
    Atomically transition a recovery case to a new state.

    Returns:
        1 if the transition succeeded.
        0 if the case was stale or another worker won the race.

    Raises:
        InvalidStateTransition if the transition is not allowed.
    """

    validate_transition(expected_status, new_status)

    result = session.execute(
        update(RecoveryCase)
        .where(
            RecoveryCase.id == case_id,
            RecoveryCase.status == expected_status,
            RecoveryCase.version == expected_version,
        )
        .values(
            status=new_status,
            version=expected_version + 1,
            updated_at=utcnow(),
        )
    )

    return max(0, result.rowcount)


def get_recovery_case_locked(
    session: Session,
    case_id: UUID,
) -> Optional[RecoveryCase]:
    """
    Pessimistic row-lock helper.

    Uses SELECT ... FOR UPDATE.

    This is useful for short critical sections, but should not be held
    while calling slow external services.
    """

    return session.execute(
        select(RecoveryCase)
        .where(RecoveryCase.id == case_id)
        .with_for_update()
    ).scalar_one_or_none()
