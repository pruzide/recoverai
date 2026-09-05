import json
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, ValidationError


class RazorpayPaymentEntity(BaseModel):
    id: str
    amount: int = Field(ge=0)
    currency: str
    status: Optional[str] = None
    error_code: Optional[str] = None
    error_description: Optional[str] = None
    notes: Optional[Dict[str, Any]] = None


class RazorpayWebhook(BaseModel):
    id: Optional[str] = None
    event: str
    payload: Dict[str, Any]


def parse_razorpay_webhook(raw_body: bytes) -> RazorpayWebhook:
    data = json.loads(raw_body)
    return RazorpayWebhook.model_validate(data)


def extract_payment_entity(webhook: RazorpayWebhook) -> RazorpayPaymentEntity:
    payment = webhook.payload.get("payment")

    if not isinstance(payment, dict):
        raise ValueError("payload.payment is missing or invalid")

    entity = payment.get("entity")

    if not isinstance(entity, dict):
        raise ValueError("payload.payment.entity is missing or invalid")

    return RazorpayPaymentEntity.model_validate(entity)