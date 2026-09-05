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
    if len(sys.argv) < 3:
        print(
            "Usage: python scripts/send_recovery_success_webhook.py "
            "MERCHANT_ID RECOVERY_CASE_ID [AMOUNT_MINOR] [EVENT_ID] [NEW_PAYMENT_ID]"
        )
        sys.exit(1)

    merchant_id = sys.argv[1]
    recovery_case_id = sys.argv[2]

    amount_minor = int(sys.argv[3]) if len(sys.argv) > 3 else 7999
    event_id = sys.argv[4] if len(sys.argv) > 4 else f"evt_{uuid.uuid4().hex}"
    new_payment_id = sys.argv[5] if len(sys.argv) > 5 else f"pay_{uuid.uuid4().hex}"

    payload = {
        "id": event_id,
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": new_payment_id,
                    "amount": amount_minor,
                    "currency": "INR",
                    "status": "captured",
                    "notes": {
                        "recoverai_merchant_id": merchant_id,
                        "recoverai_recovery_case_id": recovery_case_id,
                    },
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


if __name__ == "__main__":
    main()