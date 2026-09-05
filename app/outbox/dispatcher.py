from datetime import datetime, timezone

import structlog
from sqlalchemy import or_, select

from app.config import settings
from app.db import get_session_factory
from app.models import OutboxEvent
from app.models.enums import OutboxEventStatus
from app.tasks.recovery import process_outbox_event


logger = structlog.get_logger()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def dispatch_outbox_events(batch_size: int | None = None) -> int:
    limit = batch_size or settings.outbox_dispatch_batch_size

    SessionLocal = get_session_factory()
    dispatched = 0

    with SessionLocal() as session:
        with session.begin():
            events = session.execute(
                select(OutboxEvent)
                .where(OutboxEvent.status == OutboxEventStatus.PENDING)
                .where(
                    or_(
                        OutboxEvent.deliver_at.is_(None),
                        OutboxEvent.deliver_at <= utcnow(),
                    )
                )
                .order_by(OutboxEvent.created_at.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).scalars().all()

            for event in events:
                try:
                    process_outbox_event.apply_async(
                        args=[str(event.id)],
                        task_id=str(event.id),
                        queue=settings.celery_task_default_queue,
                    )

                    event.status = OutboxEventStatus.PUBLISHED
                    event.published_at = utcnow()
                    event.attempts += 1
                    event.last_error = None

                    dispatched += 1

                    logger.info(
                        "outbox_event_published",
                        outbox_event_id=str(event.id),
                        event_type=event.event_type,
                    )

                except Exception as exc:
                    event.attempts += 1
                    event.last_error = str(exc)[:512]

                    if event.attempts >= settings.outbox_max_dispatch_attempts:
                        event.status = OutboxEventStatus.FAILED

                    logger.warning(
                        "outbox_event_publish_failed",
                        outbox_event_id=str(event.id),
                        attempts=event.attempts,
                        error=str(exc),
                    )

    return dispatched