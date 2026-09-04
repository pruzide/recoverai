from uuid import UUID

import structlog
from sqlalchemy.exc import DBAPIError, OperationalError

from app.celery_app import celery_app
from app.db import get_session_factory
from app.domain.recovery import transition_recovery_case
from app.domain.recovery_state import InvalidStateTransition
from app.models import AuditEvent, OutboxEvent, RecoveryCase
from app.models.enums import RecoveryCaseStatus
from app.tasks.backoff import exponential_backoff_with_jitter


logger = structlog.get_logger()


def _insert_task_audit(
    session,
    case: RecoveryCase,
    outbox_event_id: str,
    from_status: RecoveryCaseStatus,
    to_status: RecoveryCaseStatus,
) -> None:
    audit = AuditEvent(
        merchant_id=case.merchant_id,
        entity_type="recovery_case",
        entity_id=str(case.id),
        event_type="recovery_case.analysis_started",
        actor="worker",
        correlation_id=None,
        payload={
            "outbox_event_id": outbox_event_id,
            "from_status": from_status.value,
            "to_status": to_status.value,
        },
    )

    session.add(audit)
    session.flush()


def _handle_recovery_case_eligible(session, outbox: OutboxEvent) -> dict:
    case_id_raw = outbox.payload.get("recovery_case_id")

    try:
        case_id = UUID(str(case_id_raw))
    except (ValueError, TypeError):
        return {
            "status": "invalid_payload",
            "reason": "missing_or_invalid_recovery_case_id",
        }

    case = session.get(RecoveryCase, case_id)

    if case is None:
        return {
            "status": "missing_recovery_case",
            "recovery_case_id": str(case_id_raw),
        }

    if case.status != RecoveryCaseStatus.ELIGIBLE:
        return {
            "status": "ignored",
            "reason": f"case_status_is_{case.status.value}",
            "recovery_case_id": str(case.id),
        }

    try:
        transition_recovery_case(case, RecoveryCaseStatus.ANALYSING)
    except InvalidStateTransition:
        return {
            "status": "ignored",
            "reason": "invalid_state_transition",
            "recovery_case_id": str(case.id),
        }

    _insert_task_audit(
        session=session,
        case=case,
        outbox_event_id=str(outbox.id),
        from_status=RecoveryCaseStatus.ELIGIBLE,
        to_status=RecoveryCaseStatus.ANALYSING,
    )

    return {
        "status": "processed",
        "recovery_case_id": str(case.id),
        "new_status": case.status.value,
    }


def _process_outbox_event(outbox_event_id: str) -> dict:
    try:
        outbox_id = UUID(outbox_event_id)
    except ValueError:
        return {
            "status": "invalid_outbox_id",
        }

    SessionLocal = get_session_factory()

    with SessionLocal() as session:
        with session.begin():
            outbox = session.get(OutboxEvent, outbox_id)

            if outbox is None:
                return {
                    "status": "missing_outbox_event",
                }

            if outbox.event_type == "recovery_case.eligible":
                return _handle_recovery_case_eligible(session, outbox)

            return {
                "status": "ignored",
                "reason": "unsupported_event_type",
                "event_type": outbox.event_type,
            }


@celery_app.task(
    bind=True,
    name="recovery.process_outbox_event",
    max_retries=5,
)
def process_outbox_event(self, outbox_event_id: str):
    logger.info(
        "task_started",
        task_name="process_outbox_event",
        outbox_event_id=outbox_event_id,
    )

    try:
        result = _process_outbox_event(outbox_event_id)

        logger.info(
            "task_completed",
            task_name="process_outbox_event",
            outbox_event_id=outbox_event_id,
            result_status=result.get("status"),
        )

        return result

    except (OperationalError, DBAPIError) as exc:
        retries = self.request.retries or 0
        delay = exponential_backoff_with_jitter(retries)

        logger.warning(
            "task_retrying",
            task_name="process_outbox_event",
            outbox_event_id=outbox_event_id,
            retry_number=retries,
            delay_seconds=delay,
            error=str(exc),
        )

        raise self.retry(exc=exc, countdown=delay)

    except Exception:
        logger.exception(
            "task_failed",
            task_name="process_outbox_event",
            outbox_event_id=outbox_event_id,
        )
        raise
