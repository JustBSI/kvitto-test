import secrets
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app


@pytest.mark.asyncio
async def test_application_exposes_documentation() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://localhost/kvitto",
        webhook_secret=secrets.token_hex(32),
    )
    application = create_app(settings)

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        schema_response = await client.get("/openapi.json")
        docs_response = await client.get("/docs")

    assert application.state.settings is settings
    assert schema_response.status_code == 200
    schema = schema_response.json()
    assert schema["info"]["title"] == "Kvitto Payment API"
    assert schema["info"]["version"] == "0.1.0"
    assert set(schema["paths"]) == {
        "/tariffs",
        "/payments",
        "/payments/{payment_id}",
        "/webhooks/bank",
    }
    assert "get" in schema["paths"]["/tariffs"]
    assert {"get", "post"} <= schema["paths"]["/payments"].keys()
    tariff_id_schema = schema["components"]["schemas"]["PaymentCreate"]["properties"][
        "tariff_id"
    ]
    assert tariff_id_schema["maximum"] == 2147483647
    webhook_operation = schema["paths"]["/webhooks/bank"]["post"]
    signature_headers = [
        parameter
        for parameter in webhook_operation["parameters"]
        if parameter["in"] == "header" and parameter["name"] == "X-Signature"
    ]
    assert len(signature_headers) == 1
    assert signature_headers[0]["required"] is True
    assert signature_headers[0]["schema"] == {"type": "string"}
    assert "401" in webhook_operation["responses"]
    webhook_schema = webhook_operation["requestBody"]
    assert webhook_schema["required"] is True
    properties = webhook_schema["content"]["application/json"]["schema"]["properties"]
    assert properties["payment_id"]["format"] == "uuid"
    assert set(properties["status"]["enum"]) == {
        "pending",
        "succeeded",
        "failed",
        "refunded",
    }
    assert docs_response.status_code == 200
    assert "SwaggerUIBundle" in docs_response.text
    assert "/openapi.json" in docs_response.text


def test_factory_requires_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in ("DATABASE_URL", "WEBHOOK_SECRET", "database_url", "webhook_secret"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValidationError) as error:
        create_app()

    assert {item["loc"] for item in error.value.errors(include_input=False)} == {
        ("database_url",),
        ("webhook_secret",),
    }
