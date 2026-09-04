import hashlib
import hmac
import json
import sys
import uuid
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import httpx

from app.config import settings


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/send_local_webhook.py MERCHANT_ID [event_type] [payment_id] [event_id]")
        sys.exit(1)

    merchant_id = sys.argv[1]
    event_type = sys.argv[2] if len(sys.argv) > 2 else "payment.failed"
    payment_id = sys.argv[3] if len(sys.argv) > 3 else f"pay_{uuid.uuid4().hex}"
    event_id = sys.argv[4] if len(sys.argv) > 4 else f"evt_{uuid.uuid4().hex}"

    status = "failed" if event_type == "payment.failed" else "captured"

    payload = {
        "id": event_id,
        "event": event_type,
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "amount": 7999,
                    "currency": "INR",
                    "status": status,
                    "error_code": "issuer_unavailable" if event_type == "payment.failed" else None,
                    "error_description": "Simulated local failure" if event_type == "payment.failed" else None,
                }
            }
        },
    }

    body = json.dumps(payload).encode("utf-8")

    signature = hmac.new(
        settings.razorpay_webhook_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    response = httpx.post(
        f"http://127.0.0.1:8000/webhooks/razorpay/{merchant_id}",
        content=body,
        headers={
            "X-Razorpay-Signature": signature,
            "Content-Type": "application/json",
        },
        timeout=10,
    )

    print(response.status_code)
    print(response.text)

    if response.status_code != 200:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
