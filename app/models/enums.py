from enum import Enum


class PaymentStatus(str, Enum):
    CREATED = "CREATED"
    FAILED = "FAILED"
    CAPTURED = "CAPTURED"


class RecoveryCaseStatus(str, Enum):
    FAILED = "FAILED"
    ELIGIBLE = "ELIGIBLE"
    ANALYSING = "ANALYSING"
    ACTION_SELECTED = "ACTION_SELECTED"
    ACTION_SCHEDULED = "ACTION_SCHEDULED"
    WAITING = "WAITING"
    RECOVERED = "RECOVERED"
    STOPPED = "STOPPED"
    ESCALATED = "ESCALATED"


class RecoveryActionType(str, Enum):
    WAIT = "WAIT"
    CREATE_PAYMENT_LINK = "CREATE_PAYMENT_LINK"
    SEND_REMINDER = "SEND_REMINDER"
    STOP = "STOP"
    ESCALATE = "ESCALATE"


class RecoveryActionStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WebhookEventStatus(str, Enum):
    RECEIVED = "RECEIVED"
    PROCESSED = "PROCESSED"
    IGNORED = "IGNORED"
    FAILED = "FAILED"


class OutboxEventStatus(str, Enum):
    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"