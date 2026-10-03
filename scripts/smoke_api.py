"""Exercise a running API with synthetic data; no secrets are printed."""

import argparse
import hmac
import json
from uuid import uuid4

import httpx

from app.config import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    settings = Settings()
    with httpx.Client(base_url=args.base_url, timeout=10) as client:
        tariffs_response = client.get("/tariffs")
        assert tariffs_response.status_code == 200
        tariffs = tariffs_response.json()
        assert [(t["title"], t["price"]) for t in tariffs] == [
            ("basic", 990000),
            ("standard", 1990000),
            ("premium", 2990000),
        ]
        email = f"smoke-{uuid4().hex}@example.com"
        payload = {"tariff_id": tariffs[1]["id"], "email": email, "method": "card"}
        headers = {"Idempotency-Key": uuid4().hex}
        created = client.post("/payments", json=payload, headers=headers)
        assert created.status_code == 201
        card = created.json()
        assert card["amount"] == 1990000 and card["discount"] == 0
        assert card["schedule"] is None and card["status"] == "pending"
        repeated = client.post("/payments", json=payload, headers=headers)
        assert repeated.status_code == 200 and repeated.json() == card
        assert client.get(f"/payments/{card['id']}").json() == card
        installment_response = client.post(
            "/payments",
            json={
                **payload,
                "method": "installment",
                "installment_months": 3,
                "promo_code": "kvitto10",
            },
        )
        assert installment_response.status_code == 201
        installment = installment_response.json()
        assert installment["amount"] == 1791000 and installment["discount"] == 199000
        assert installment["schedule"] == [597000] * 3
        for status in ["succeeded", "refunded", "failed"]:
            body = json.dumps({"payment_id": card["id"], "status": status}).encode()
            signature = hmac.new(
                settings.webhook_secret.get_secret_value().encode(), body, "sha256"
            ).hexdigest()
            response = client.post(
                "/webhooks/bank", content=body, headers={"X-Signature": signature}
            )
            if status == "failed":
                assert response.status_code == 409
                assert response.json() == {"error": "invalid_transition"}
            else:
                assert response.status_code == 200
                assert response.json() == {"result": "ok"}
        assert client.get(f"/payments/{card['id']}").json()["status"] == "refunded"
        unsigned = client.post(
            "/webhooks/bank",
            json={
                "payment_id": installment["id"],
                "status": "succeeded",
            },
        )
        assert unsigned.status_code == 401
        filtered = client.get("/payments", params={"email": email, "status": "pending"})
        assert filtered.status_code == 200
        assert [p["id"] for p in filtered.json()] == [installment["id"]]
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200
    print("Live API smoke checks passed")


if __name__ == "__main__":
    main()
