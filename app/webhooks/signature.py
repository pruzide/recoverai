import hashlib
import hmac
from typing import Optional

from app.config import settings


class WebhookSignatureError(ValueError):
    pass


def verify_razorpay_signature(raw_body: bytes, signature_header: Optional[str]) -> None:
    secret = settings.razorpay_webhook_secret

    if not secret:
        raise WebhookSignatureError("webhook secret is not configured")

    if not signature_header:
        raise WebhookSignatureError("missing webhook signature header")

    expected_signature = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, signature_header.strip()):
        raise WebhookSignatureError("invalid webhook signature")