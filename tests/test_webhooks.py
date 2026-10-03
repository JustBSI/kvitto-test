import asyncio
import hmac
import json
import secrets
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.business import PaymentStatus
from app.config import Settings
from app.models import Payment

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def payment(client: AsyncClient) -> dict[str, object]:
    tariffs = (await client.get("/tariffs")).json()
    response = await client.post(
        "/payments",
        json={
            "tariff_id": tariffs[0]["id"],
            "email": "student@example.com",
            "method": "card",
        },
    )
    assert response.status_code == 201
    return response.json()


def signature(body: bytes, settings: Settings) -> str:
    return hmac.new(
        settings.webhook_secret.get_secret_value().encode(), body, "sha256"
    ).hexdigest()


def webhook_body(payment_id: str, status: str) -> bytes:
    # Whitespace/order differ from normal JSON serialization on purpose.
    return f'{{ "status" : "{status}",\n "payment_id" : "{payment_id}" }}'.encode()


@pytest.mark.parametrize("current", list(PaymentStatus))
@pytest.mark.parametrize("target", list(PaymentStatus))
async def test_webhook_transitions_and_database_state(
    client: AsyncClient,
    payment: dict[str, object],
    test_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    current: PaymentStatus,
    target: PaymentStatus,
) -> None:
    payment_id = UUID(payment["id"])
    async with session_factory() as session, session.begin():
        await session.execute(
            update(Payment).where(Payment.id == payment_id).values(status=current.value)
        )
    before = (await client.get(f"/payments/{payment_id}")).json()
    body = webhook_body(str(payment_id), target.value)
    response = await client.post(
        "/webhooks/bank",
        content=body,
        headers={"X-Signature": signature(body, test_settings)},
    )
    allowed = (current, target) in {
        (PaymentStatus.PENDING, PaymentStatus.SUCCEEDED),
        (PaymentStatus.PENDING, PaymentStatus.FAILED),
        (PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED),
    }
    after = (await client.get(f"/payments/{payment_id}")).json()
    if allowed:
        assert response.status_code == 200
        assert response.json() == {"result": "ok"}
        assert after == {**before, "status": target.value}
    else:
        assert response.status_code == 409
        assert response.json() == {"error": "invalid_transition"}
        assert after == before
    async with session_factory() as session:
        persisted = await session.get(Payment, payment_id)
        assert persisted.status == (target.value if allowed else current.value)
        assert persisted.amount == payment["amount"]


async def test_success_then_refund(
    client: AsyncClient,
    payment: dict[str, object],
    test_settings: Settings,
) -> None:
    for status in ["succeeded", "refunded"]:
        body = webhook_body(payment["id"], status)
        response = await client.post(
            "/webhooks/bank",
            content=body,
            headers={"X-Signature": signature(body, test_settings).upper()},
        )
        assert response.status_code == 200
        assert response.json() == {"result": "ok"}
    assert (await client.get(f"/payments/{payment['id']}")).json()[
        "status"
    ] == "refunded"


@pytest.mark.parametrize("bad_signature", [None, "", "bad", "00" * 32, "z" * 64])
async def test_bad_signature_does_not_write(
    client: AsyncClient,
    payment: dict[str, object],
    bad_signature: str | None,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    body = webhook_body(payment["id"], "succeeded")
    headers = {} if bad_signature is None else {"X-Signature": bad_signature}
    response = await client.post("/webhooks/bank", content=body, headers=headers)
    assert response.status_code == 401
    assert response.json() == {"detail": "invalid_signature"}
    assert (await client.get(f"/payments/{payment['id']}")).json() == payment
    async with session_factory() as session:
        persisted = await session.get(Payment, UUID(payment["id"]))
        assert persisted.status == "pending"


async def test_signature_is_for_raw_body(
    client: AsyncClient,
    payment: dict[str, object],
    test_settings: Settings,
) -> None:
    raw_body = webhook_body(payment["id"], "succeeded")
    reserialized = json.dumps(json.loads(raw_body)).encode()
    assert raw_body != reserialized
    for body, signed_body in [(raw_body, reserialized), (raw_body + b" ", raw_body)]:
        response = await client.post(
            "/webhooks/bank",
            content=body,
            headers={"X-Signature": signature(signed_body, test_settings)},
        )
        assert response.status_code == 401
    assert (await client.get(f"/payments/{payment['id']}")).json() == payment


async def test_other_secret_is_rejected(
    client: AsyncClient,
    payment: dict[str, object],
) -> None:
    body = webhook_body(payment["id"], "succeeded")
    wrong_signature = hmac.new(secrets.token_bytes(32), body, "sha256").hexdigest()
    response = await client.post(
        "/webhooks/bank", content=body, headers={"X-Signature": wrong_signature}
    )
    assert response.status_code == 401
    assert (await client.get(f"/payments/{payment['id']}")).json() == payment


async def test_unknown_payment(client: AsyncClient, test_settings: Settings) -> None:
    body = webhook_body(str(uuid4()), "succeeded")
    response = await client.post(
        "/webhooks/bank",
        content=body,
        headers={"X-Signature": signature(body, test_settings)},
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "payment_not_found"}


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"null",
        b"[]",
        b"1",
        b"\xff",
        b"not-json",
        b"{}",
        b'{"payment_id":"invalid"}',
        b'{"payment_id":"00000000-0000-0000-0000-000000000000","status":"other"}',
        b'{"payment_id":"00000000-0000-0000-0000-000000000000","status":null}',
        b'{"payment_id":"00000000-0000-0000-0000-000000000000","status":1}',
    ],
)
async def test_signature_checked_before_validation(
    client: AsyncClient,
    payment: dict[str, object],
    test_settings: Settings,
    body: bytes,
) -> None:
    unsigned = await client.post("/webhooks/bank", content=body)
    assert unsigned.status_code == 401
    signed = await client.post(
        "/webhooks/bank",
        content=body,
        headers={"X-Signature": signature(body, test_settings)},
    )
    assert signed.status_code == 422
    assert "detail" in signed.json()
    assert (await client.get(f"/payments/{payment['id']}")).json() == payment


async def test_concurrent_webhooks_serialize_status_changes(
    client: AsyncClient,
    payment: dict[str, object],
    test_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    body = webhook_body(payment["id"], "succeeded")
    responses = await asyncio.gather(
        *[
            client.post(
                "/webhooks/bank",
                content=body,
                headers={"X-Signature": signature(body, test_settings)},
            )
            for _ in range(2)
        ]
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    async with session_factory() as session:
        statuses = list(await session.scalars(select(Payment.status)))
    assert statuses == ["succeeded"]


async def test_webhook_rechecks_status_after_waiting_for_row_lock(
    client: AsyncClient,
    payment: dict[str, object],
    test_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    payment_id = UUID(payment["id"])
    body = webhook_body(str(payment_id), "succeeded")
    request_task = None
    try:
        async with asyncio.timeout(10):
            async with session_factory() as blocker, blocker.begin():
                locked = await blocker.scalar(
                    select(Payment).where(Payment.id == payment_id).with_for_update()
                )
                assert locked is not None and locked.status == "pending"
                blocker_pid = await blocker.scalar(text("SELECT pg_backend_pid()"))
                request_task = asyncio.create_task(
                    client.post(
                        "/webhooks/bank",
                        content=body,
                        headers={"X-Signature": signature(body, test_settings)},
                    )
                )
                # Observe an actual database wait, not merely concurrent task creation.
                async with session_factory() as observer:
                    while not await observer.scalar(
                        text("""
                            SELECT EXISTS (
                                SELECT 1 FROM pg_locks
                                WHERE NOT granted
                                  AND :blocker_pid = ANY(pg_blocking_pids(pid))
                            )
                        """),
                        {"blocker_pid": blocker_pid},
                    ):
                        assert not request_task.done(), (
                            "Webhook did not wait for the lock"
                        )
                        await asyncio.sleep(0.01)
                # The waiting webhook must now reject failed -> succeeded.
                await blocker.execute(
                    update(Payment)
                    .where(Payment.id == payment_id)
                    .values(status="failed")
                )
            response = await request_task
        assert response.status_code == 409
        assert response.json() == {"error": "invalid_transition"}
        assert (await client.get(f"/payments/{payment_id}")).json() == {
            **payment,
            "status": "failed",
        }
        async with session_factory() as session:
            persisted = await session.get(Payment, payment_id)
            assert persisted is not None and persisted.status == "failed"
    finally:
        if request_task is not None:
            request_task.cancel()
            await asyncio.gather(request_task, return_exceptions=True)
