"""Send a signed demo webhook; never print the secret or the signature."""

import argparse
import hmac
import json
from uuid import UUID

import httpx

from app.business import PaymentStatus
from app.config import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payment_id", type=UUID)
    parser.add_argument("status", choices=[status.value for status in PaymentStatus])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    settings = Settings()
    body = json.dumps(
        {"payment_id": str(args.payment_id), "status": args.status}
    ).encode()
    signature = hmac.new(
        settings.webhook_secret.get_secret_value().encode(), body, "sha256"
    ).hexdigest()
    response = httpx.post(
        f"{args.base_url.rstrip('/')}/webhooks/bank",
        content=body,
        headers={"Content-Type": "application/json", "X-Signature": signature},
        timeout=10,
    )
    print(f"HTTP {response.status_code}: {response.text}")
    response.raise_for_status()


if __name__ == "__main__":
    main()
