import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import PaymentStatus


class Payment(TimestampMixin, Base):
    __tablename__ = "payments"

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

    provider: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="razorpay",
        server_default="razorpay",
    )

    provider_payment_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(
            PaymentStatus,
            native_enum=False,
            length=32,
            create_constraint=True,
        ),
        nullable=False,
        default=PaymentStatus.CREATED,
        server_default=PaymentStatus.CREATED.value,
    )

    amount_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    failure_code: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
    )

    failure_reason: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
    )

    failed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    captured_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "merchant_id",
            "provider",
            "provider_payment_id",
            name="uq_payments_merchant_provider_payment",
        ),
        CheckConstraint(
            "amount_minor >= 0",
            name="ck_payments_amount_minor_nonnegative",
        ),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="ck_payments_currency_three_uppercase",
        ),
        Index(
            "ix_payments_merchant_status",
            "merchant_id",
            "status",
        ),
    )
