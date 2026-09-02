from app.domain.recovery_state import validate_transition
from app.models.enums import RecoveryCaseStatus
from app.models.recovery import RecoveryCase


def transition_recovery_case(
    case: RecoveryCase,
    new_status: RecoveryCaseStatus,
) -> None:
    validate_transition(case.status, new_status)

    if case.status != new_status:
        case.status = new_status
        case.version += 1
