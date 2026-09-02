from app.models.enums import RecoveryCaseStatus


class InvalidStateTransition(ValueError):
    pass


TERMINAL_STATES = {
    RecoveryCaseStatus.RECOVERED,
    RecoveryCaseStatus.STOPPED,
    RecoveryCaseStatus.ESCALATED,
}


ALLOWED_TRANSITIONS = {
    RecoveryCaseStatus.FAILED: {
        RecoveryCaseStatus.ELIGIBLE,
        RecoveryCaseStatus.STOPPED,
        RecoveryCaseStatus.RECOVERED,
    },
    RecoveryCaseStatus.ELIGIBLE: {
        RecoveryCaseStatus.ANALYSING,
        RecoveryCaseStatus.STOPPED,
        RecoveryCaseStatus.RECOVERED,
    },
    RecoveryCaseStatus.ANALYSING: {
        RecoveryCaseStatus.ACTION_SELECTED,
        RecoveryCaseStatus.WAITING,
        RecoveryCaseStatus.STOPPED,
        RecoveryCaseStatus.ESCALATED,
        RecoveryCaseStatus.RECOVERED,
    },
    RecoveryCaseStatus.ACTION_SELECTED: {
        RecoveryCaseStatus.ACTION_SCHEDULED,
        RecoveryCaseStatus.STOPPED,
        RecoveryCaseStatus.ESCALATED,
        RecoveryCaseStatus.RECOVERED,
    },
    RecoveryCaseStatus.ACTION_SCHEDULED: {
        RecoveryCaseStatus.WAITING,
        RecoveryCaseStatus.STOPPED,
        RecoveryCaseStatus.ESCALATED,
        RecoveryCaseStatus.RECOVERED,
    },
    RecoveryCaseStatus.WAITING: {
        RecoveryCaseStatus.ACTION_SELECTED,
        RecoveryCaseStatus.ANALYSING,
        RecoveryCaseStatus.RECOVERED,
        RecoveryCaseStatus.STOPPED,
        RecoveryCaseStatus.ESCALATED,
    },
    RecoveryCaseStatus.RECOVERED: set(),
    RecoveryCaseStatus.STOPPED: set(),
    RecoveryCaseStatus.ESCALATED: set(),
}


def is_terminal(status: RecoveryCaseStatus) -> bool:
    return status in TERMINAL_STATES


def can_transition(
    current: RecoveryCaseStatus,
    new: RecoveryCaseStatus,
) -> bool:
    return new in ALLOWED_TRANSITIONS.get(current, set())


def validate_transition(
    current: RecoveryCaseStatus,
    new: RecoveryCaseStatus,
) -> None:
    if current == new:
        return

    if is_terminal(current):
        raise InvalidStateTransition(
            f"Cannot transition from terminal state {current.value} to {new.value}"
        )

    if not can_transition(current, new):
        raise InvalidStateTransition(
            f"Invalid recovery case transition: {current.value} -> {new.value}"
        )
