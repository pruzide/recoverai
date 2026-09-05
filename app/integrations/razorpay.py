import uuid

import httpx

from app.config import settings


class RazorpayError(Exception):
    pass


class RazorpayTimeoutError(RazorpayError):
    pass


def create_payment_link(
    *,
    amount_minor: int,
    currency: str,
    description: str,
    reference_id: str,
    notes: dict,
) -> dict:
    if settings.razorpay_use_mock:
        link_id = f"link_mock_{uuid.uuid4().hex[:14]}"
        short_url = f"https://rzp.io/l/mock_{uuid.uuid4().hex[:8]}"

        return {
            "id": link_id,
            "short_url": short_url,
            "status": "created",
            "mock": True,
        }

    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise RazorpayError("Razorpay credentials are not configured")

    payload = {
        "amount": amount_minor,
        "currency": currency,
        "description": description,
        "reference_id": reference_id,
        "notes": notes,
    }

    try:
        response = httpx.post(
            "https://api.razorpay.com/v1/payment_links",
            json=payload,
            auth=(
                settings.razorpay_key_id,
                settings.razorpay_key_secret,
            ),
            timeout=settings.razorpay_timeout_seconds,
        )

        if response.status_code >= 400:
            raise RazorpayError(
                f"Razorpay error {response.status_code}: {response.text[:300]}"
            )

        data = response.json()

        return {
            "id": data.get("id"),
            "short_url": data.get("short_url"),
            "status": data.get("status"),
        }

    except httpx.TimeoutException as exc:
        raise RazorpayTimeoutError("Razorpay request timed out") from exc

    except httpx.HTTPError as exc:
        raise RazorpayError(f"Razorpay HTTP error: {exc}") from exc