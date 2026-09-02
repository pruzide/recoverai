import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import (
    RecoveryActionStatus,
    RecoveryActionType,
    RecoveryCaseStatus,
)


class RecoveryCase(TimestampMixin, Base):
    __tablename__ = "recovery_cases"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=True,
        default=uuid.uuid4,
    )

    merchant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("merchants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    payment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
    )

    status: Mapped[RecoveryCaseStatus] = mapped_column(
        SAEnum(
            RecoveryCaseStatus,
            native_enum=False,
            length=32,
            create_constraint=True,
        ),
        nullable=False,
        default=RecoveryCaseStatus.FAILED,
        server_default=RecoveryCaseStatus.FAILED.value,
    )

    amount_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    failure_category: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
    )

    next_action_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )

    __table_args__ = (
        UniqueConstraint(
            "payment_id",
            name="uq_recovery_cases_payment_id",
        ),
        CheckConstraint(
            "amount_minor >= 0",
            name="ck_recovery_cases_amount_minor_nonnegative",
        ),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="ck_recovery_cases_currency_three_uppercase",
        ),
        CheckConstraint(
            "version > 0",
            name="ck_recovery_cases_version_positive",
        ),
        Index(
            "ix_recovery_cases_merchant_status_next",
            "merchant_id",
            "status",
            "next_action_at",
        ),
        Index(
            "ix_recovery_cases_status_next_action_at",
            "status",
            "next_action_at",
        ),
    )


class RecoveryAction(TimestampMixin, Base):
    __tablename__ = "recovery_actions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=True,
        default=uuid.uuid4,
    )

    merchant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("merchants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    recovery_case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recovery_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    action_type: Mapped[RecoveryActionType] = mapped_column(
        SAEnum(
            RecoveryActionType,
            native_enum=False,
            length=32,
            create_constraint=True,
        ),
        nullable=False,
    )

    status: Mapped[RecoveryActionStatus] = mapped_column(
        SAEnum(
            RecoveryActionStatus,
            native_enum=False,
            length=32,
            create_constraint=True,
        ),
        nullable=False,
        default=RecoveryActionStatus.PENDING,
        server_default=RecoveryActionStatus.PENDING.value,
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
    )

    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )

    provider_reference: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
    )

    scheduled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    executed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    failure_reason: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "recovery_case_id",
            "action_type",
            "attempt_number",
            name="uq_recovery_actions_case_type_attempt",
        ),
        CheckConstraint(
            "attempt_number > 0",
            name="ck_recovery_actions_attempt_number_positive",
        ),
        Index(
            "ix_recovery_actions_merchant_status",
            "merchant_id",
            "status",
        ),
        Index(
            "ix_recovery_actions_case_status",
            "recovery_case_id",
            "status",
        ),
    )
