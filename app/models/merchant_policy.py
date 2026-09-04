import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    UniqueConstraint,
    Uuid,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class MerchantPolicy(TimestampMixin, Base):
    __tablename__ = "merchant_policies"

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

    max_actions_per_case: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
        server_default="3",
    )

    max_reminders_per_case: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=2,
        server_default="2",
    )

    one_active_payment_link: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )

    high_value_escalation_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )

    high_value_threshold_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=500_000,
        server_default="500000",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )

    __table_args__ = (
        UniqueConstraint(
            "merchant_id",
            name="uq_merchant_policies_merchant_id",
        ),
        CheckConstraint(
            "max_actions_per_case >= 0",
            name="ck_merchant_policies_max_actions_nonnegative",
        ),
        CheckConstraint(
            "max_reminders_per_case >= 0",
            name="ck_merchant_policies_max_reminders_nonnegative",
        ),
        CheckConstraint(
            "high_value_threshold_minor >= 0",
            name="ck_merchant_policies_high_value_threshold_nonnegative",
        ),
    )
