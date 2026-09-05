import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import OutboxEventStatus


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

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

    aggregate_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    aggregate_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
    )

    status: Mapped[OutboxEventStatus] = mapped_column(
        SAEnum(
            OutboxEventStatus,
            native_enum=False,
            length=32,
            create_constraint=True,
        ),
        nullable=False,
        default=OutboxEventStatus.PENDING,
        server_default=OutboxEventStatus.PENDING.value,
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    last_error: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    deliver_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "attempts >= 0",
            name="ck_outbox_events_attempts_nonnegative",
        ),
        Index(
            "ix_outbox_events_status_created_at",
            "status",
            "created_at",
        ),
        Index(
            "ix_outbox_events_status_deliver_at",
            "status",
            "deliver_at",
        ),
        Index(
            "ix_outbox_events_merchant_status",
            "merchant_id",
            "status",
        ),
    )