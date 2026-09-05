from app.models.enums import RecoveryActionType
from app.simulation.population import SimulatedPayment


def baseline_decide(payment: SimulatedPayment) -> RecoveryActionType:
    return RecoveryActionType.SEND_REMINDER