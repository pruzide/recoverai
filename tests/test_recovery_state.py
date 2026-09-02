import pytest

from app.domain.recovery_state import (
    InvalidStateTransition,
    validate_transition,
)
from app.models.enums import RecoveryCaseStatus


def test_failed_to_eligible():
    validate_transition(
        RecoveryCaseStatus.FAILED,
        RecoveryCaseStatus.ELIGIBLE,
    )


def test_waiting_to_recovered():
    validate_transition(
        RecoveryCaseStatus.WAITING,
        RecoveryCaseStatus.RECOVERED,
    )


def test_recovered_cannot_regress():
    with pytest.raises(InvalidStateTransition):
        validate_transition(
            RecoveryCaseStatus.RECOVERED,
            RecoveryCaseStatus.WAITING,
        )


def test_stopped_cannot_regress():
    with pytest.raises(InvalidStateTransition):
        validate_transition(
            RecoveryCaseStatus.STOPPED,
            RecoveryCaseStatus.ANALYSING,
        )


def test_escalated_cannot_regress():
    with pytest.raises(InvalidStateTransition):
        validate_transition(
            RecoveryCaseStatus.ESCALATED,
            RecoveryCaseStatus.ELIGIBLE,
        )


def test_same_state_is_allowed_as_idempotent_noop():
    validate_transition(
        RecoveryCaseStatus.RECOVERED,
        RecoveryCaseStatus.RECOVERED,
    )
