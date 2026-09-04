import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from structlog.contextvars import bind_contextvars

from app.db import get_session_factory
from app.domain.money import MoneyError
from app.models import Merchant, WebhookEvent
from app.models.enums import WebhookEventStatus
from .handlers import process_razorpay_event
from .razorpay_schemas import parse_razorpay_webhook
from .signature import WebhookSignatureError, verify_razorpay_signature


router = APIRouter()
logger = structlog.get_logger()


class MerchantNotFoundError(Exception):
    pass


class DuplicateWebhookError(Exception):
    pass


def extract_provider_event_id(webhook_dto, raw_body: bytes) -> str:
    if webhook_dto.id:
        return webhook_dto.id

    return "sha256:" + hashlib.sha256(raw_body).hexdigest()


@router.post("/webhooks/razorpay/{merchant_id}")
async def razorpay_webhook(merchant_id: UUID, request: Request):
    raw_body = await request.body()

    try:
        verify_razorpay_signature(
            raw_body=raw_body,
            signature_header=request.headers.get("X-Razorpay-Signature"),
        )
    except WebhookSignatureError as exc:
        logger.warning(
            "webhook_signature_rejected",
            reason=str(exc),
        )
        return JSONResponse(
            status_code=401,
            content={
                "status": "rejected",
                "reason": "invalid_signature",
            },
        )

    try:
        webhook_dto = parse_razorpay_webhook(raw_body)
    except (json.JSONDecodeError, ValidationError, ValueError, UnicodeDecodeError) as exc:
        logger.warning(
            "webhook_payload_invalid",
            reason=str(exc),
        )
        return JSONResponse(
            status_code=400,
            content={
                "status": "rejected",
                "reason": "invalid_payload",
            },
        )

    provider_event_id = extract_provider_event_id(webhook_dto, raw_body)

    bind_contextvars(
        merchant_id=str(merchant_id),
        provider_event_id=provider_event_id,
        event_type=webhook_dto.event,
    )

    SessionLocal = get_session_factory()

    try:
        with SessionLocal() as session:
            with session.begin():
                merchant = session.get(Merchant, merchant_id)

                if merchant is None or not merchant.is_active:
                    raise MerchantNotFoundError()

                webhook_row = WebhookEvent(
                    merchant_id=merchant.id,
                    provider="razorpay",
                    provider_event_id=provider_event_id,
                    event_type=webhook_dto.event,
                    payload=webhook_dto.model_dump(),
                    status=WebhookEventStatus.RECEIVED,
                )

                session.add(webhook_row)

                try:
                    session.flush()
                except IntegrityError as exc:
                    raise DuplicateWebhookError() from exc

                correlation_id = getattr(request.state, "request_id", None)

                result = process_razorpay_event(
                    session=session,
                    merchant=merchant,
                    webhook=webhook_row,
                    event=webhook_dto,
                    correlation_id=correlation_id,
                )

                webhook_row.processed_at = datetime.now(timezone.utc)

        logger.info(
            "webhook_processed",
            outcome=result.get("outcome"),
        )

        return JSONResponse(
            status_code=200,
            content=result,
        )

    except MerchantNotFoundError:
        return JSONResponse(
            status_code=404,
            content={
                "status": "rejected",
                "reason": "merchant_not_found",
            },
        )

    except DuplicateWebhookError:
        logger.info("webhook_duplicate")
        return JSONResponse(
            status_code=200,
            content={
                "status": "duplicate",
            },
        )

    except IntegrityError:
        logger.warning(
            "webhook_conflict_treated_as_duplicate",
            exc_info=True,
        )
        return JSONResponse(
            status_code=200,
            content={
                "status": "duplicate",
            },
        )

    except (ValueError, ValidationError, MoneyError) as exc:
        logger.warning(
            "webhook_business_payload_invalid",
            reason=str(exc),
        )
        return JSONResponse(
            status_code=400,
            content={
                "status": "rejected",
                "reason": "invalid_payload",
            },
        )

    except Exception:
        logger.exception("webhook_processing_failed")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
            },
        )