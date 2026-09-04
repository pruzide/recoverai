import uuid

from app.models import Merchant, OutboxEvent
from app.models.enums import OutboxEventStatus
from app.outbox.dispatcher import dispatch_outbox_events


def create_merchant(db_session):
    merchant = Merchant(name="Dispatcher Merchant")
    db_session.add(merchant)
    db_session.commit()
    return merchant


def create_pending_outbox(db_session, merchant, attempts=0):
    outbox = OutboxEvent(
        merchant_id=merchant.id,
        aggregate_type="recovery_case",
        aggregate_id=str(uuid.uuid4()),
        event_type="recovery_case.eligible",
        payload={
            "recovery_case_id": str(uuid.uuid4()),
        },
        idempotency_key=f"test:{uuid.uuid4().hex}",
        status=OutboxEventStatus.PENDING,
        attempts=attempts,
    )

    db_session.add(outbox)
    db_session.commit()

    return outbox


def test_dispatcher_marks_event_published(db_session, monkeypatch):
    merchant = create_merchant(db_session)
    outbox = create_pending_outbox(db_session, merchant)

    calls = []

    def fake_apply_async(args=None, task_id=None, queue=None, **kwargs):
        calls.append(
            {
                "args": args,
                "task_id": task_id,
                "queue": queue,
            }
        )

    monkeypatch.setattr(
        "app.outbox.dispatcher.process_outbox_event.apply_async",
        fake_apply_async,
    )

    dispatched = dispatch_outbox_events()

    assert dispatched == 1
    assert len(calls) == 1
    assert calls[0]["args"] == [str(outbox.id)]

    db_session.expire_all()

    refreshed = db_session.get(OutboxEvent, outbox.id)

    assert refreshed.status == OutboxEventStatus.PUBLISHED
    assert refreshed.published_at is not None
    assert refreshed.attempts == 1


def test_dispatcher_keeps_event_pending_when_publish_fails(db_session, monkeypatch):
    merchant = create_merchant(db_session)
    outbox = create_pending_outbox(db_session, merchant)

    def fake_apply_async(*args, **kwargs):
        raise RuntimeError("redis down")

    monkeypatch.setattr(
        "app.outbox.dispatcher.process_outbox_event.apply_async",
        fake_apply_async,
    )

    dispatched = dispatch_outbox_events()

    assert dispatched == 0

    db_session.expire_all()

    refreshed = db_session.get(OutboxEvent, outbox.id)

    assert refreshed.status == OutboxEventStatus.PENDING
    assert refreshed.attempts == 1
    assert "redis down" in refreshed.last_error


def test_dispatcher_marks_event_failed_after_max_attempts(db_session, monkeypatch):
    merchant = create_merchant(db_session)

    outbox = create_pending_outbox(
        db_session,
        merchant,
        attempts=9,
    )

    def fake_apply_async(*args, **kwargs):
        raise RuntimeError("redis still down")

    monkeypatch.setattr(
        "app.outbox.dispatcher.process_outbox_event.apply_async",
        fake_apply_async,
    )

    dispatched = dispatch_outbox_events()

    assert dispatched == 0

    db_session.expire_all()

    refreshed = db_session.get(OutboxEvent, outbox.id)

    assert refreshed.status == OutboxEventStatus.FAILED
    assert refreshed.attempts == 10
