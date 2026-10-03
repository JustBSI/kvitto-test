import asyncio
from datetime import datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Payment

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def payment_body(client: AsyncClient) -> dict[str, object]:
    tariffs = (await client.get("/tariffs")).json()
    return {
        "tariff_id": tariffs[1]["id"],
        "email": "student@example.com",
        "method": "card",
    }


async def row_count(session_factory: async_sessionmaker[AsyncSession]) -> int:
    async with session_factory() as session:
        return await session.scalar(select(func.count()).select_from(Payment))


@pytest.mark.parametrize("promo", [None, "KVITTO10", "kvitto10", "Kvitto10"])
async def test_create_payment(
    client: AsyncClient,
    payment_body: dict[str, object],
    session_factory: async_sessionmaker[AsyncSession],
    promo: str | None,
) -> None:
    response = await client.post(
        "/payments", json={**payment_body, "promo_code": promo}
    )

    assert response.status_code == 201
    data = response.json()
    discount = 0 if promo is None else 199000
    assert set(data) == {
        "id",
        "status",
        "tariff_id",
        "amount",
        "discount",
        "method",
        "installment_months",
        "schedule",
        "email",
        "created_at",
    }
    assert data["status"] == "pending"
    assert data["tariff_id"] == payment_body["tariff_id"]
    assert data["email"] == payment_body["email"]
    assert data["method"] == "card"
    assert data["discount"] == discount
    assert data["amount"] == 1990000 - discount
    assert type(data["amount"]) is int
    assert data["installment_months"] is None
    assert data["schedule"] is None
    assert datetime.fromisoformat(data["created_at"]).utcoffset() is not None
    async with session_factory() as session:
        payment = await session.get(Payment, UUID(data["id"]))
        assert payment is not None
        assert payment.status == "pending"
        assert payment.amount == data["amount"]
        assert payment.discount == discount
        assert payment.email == data["email"]
        assert payment.created_at.utcoffset() is not None
        assert payment.idempotency_key is None
    assert await row_count(session_factory) == 1


@pytest.mark.parametrize("months", [3, 6, 12])
@pytest.mark.parametrize("promo", [None, "KVITTO10"])
async def test_installment(
    client: AsyncClient, payment_body: dict[str, object], months: int, promo: str | None
) -> None:
    response = await client.post(
        "/payments",
        json={
            **payment_body,
            "method": "installment",
            "installment_months": months,
            "promo_code": promo,
        },
    )

    assert response.status_code == 201
    data = response.json()
    expected_amount = 1990000 if promo is None else 1791000
    assert data["amount"] == expected_amount
    assert data["discount"] == 1990000 - expected_amount
    assert data["installment_months"] == months
    schedule = data["schedule"]
    assert len(schedule) == months
    assert sum(schedule) == expected_amount
    assert max(schedule) - min(schedule) <= 1
    assert schedule == sorted(schedule, reverse=True)
    assert all(type(amount) is int for amount in schedule)
    if months == 3 and promo is None:
        assert schedule == [663334, 663333, 663333]
    retrieved = await client.get(f"/payments/{data['id']}")
    assert retrieved.json() == data


async def test_sbp(client: AsyncClient, payment_body: dict[str, object]) -> None:
    response = await client.post("/payments", json={**payment_body, "method": "sbp"})
    assert response.status_code == 201
    assert response.json()["method"] == "sbp"
    assert response.json()["schedule"] is None
    assert response.json()["amount"] == 1990000


@pytest.mark.parametrize("method", ["card", "sbp"])
async def test_card_and_sbp_accept_explicit_null_months(
    client: AsyncClient,
    payment_body: dict[str, object],
    session_factory: async_sessionmaker[AsyncSession],
    method: str,
) -> None:
    response = await client.post(
        "/payments",
        json={**payment_body, "method": method, "installment_months": None},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["method"] == method
    assert data["amount"] == 1990000
    assert data["schedule"] is None
    assert data["installment_months"] is None
    async with session_factory() as session:
        saved = await session.get(Payment, UUID(data["id"]))
        assert saved.method == method
        assert saved.installment_months is None
    assert await row_count(session_factory) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"promo_code": "unknown"},
        {"promo_code": ""},
        {"method": "cash"},
        {"method": "installment"},
        {"method": "installment", "installment_months": 4},
        {"method": "installment", "installment_months": None},
        {"method": "installment", "installment_months": 3.0},
        {"method": "installment", "installment_months": "3"},
        {"method": "card", "installment_months": 3},
        {"method": "sbp", "installment_months": 6},
        {"email": "invalid"},
        {"tariff_id": True},
        {"tariff_id": 0},
    ],
)
async def test_invalid_payment_does_not_write(
    client: AsyncClient,
    payment_body: dict[str, object],
    session_factory: async_sessionmaker[AsyncSession],
    changes: dict[str, object],
) -> None:
    response = await client.post("/payments", json={**payment_body, **changes})
    assert response.status_code == 422
    assert "detail" in response.json()
    assert await row_count(session_factory) == 0


@pytest.mark.parametrize("tariff_id", [999999, 2147483647])
async def test_missing_tariff(
    client: AsyncClient,
    payment_body: dict[str, object],
    session_factory: async_sessionmaker[AsyncSession],
    tariff_id: int,
) -> None:
    response = await client.post(
        "/payments", json={**payment_body, "tariff_id": tariff_id}
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "tariff_not_found"}
    assert await row_count(session_factory) == 0


@pytest.mark.parametrize("tariff_id", [2147483648, 9223372036854775808])
async def test_tariff_id_out_of_database_range_does_not_write(
    client: AsyncClient,
    payment_body: dict[str, object],
    session_factory: async_sessionmaker[AsyncSession],
    tariff_id: int,
) -> None:
    created = await client.post("/payments", json=payment_body)
    assert created.status_code == 201
    original = created.json()

    response = await client.post(
        "/payments", json={**payment_body, "tariff_id": tariff_id}
    )

    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["loc"] == ["body", "tariff_id"]
    assert error["type"] == "less_than_equal"
    assert error["ctx"]["le"] == 2147483647
    assert await row_count(session_factory) == 1
    unchanged = await client.get(f"/payments/{original['id']}")
    assert unchanged.status_code == 200
    assert unchanged.json() == original


async def test_idempotency_returns_original(
    client: AsyncClient,
    payment_body: dict[str, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers = {"Idempotency-Key": "same-request"}
    first = await client.post("/payments", json=payment_body, headers=headers)
    repeated = await client.post("/payments", json=payment_body, headers=headers)
    different = await client.post(
        "/payments",
        json={
            **payment_body,
            "email": "other@example.com",
            "promo_code": "KVITTO10",
        },
        headers=headers,
    )
    assert first.status_code == 201
    assert repeated.status_code == different.status_code == 200
    assert first.json() == repeated.json() == different.json()
    assert await row_count(session_factory) == 1


@pytest.mark.parametrize("length", [0, 255, 256])
async def test_idempotency_key_length(
    client: AsyncClient,
    payment_body: dict[str, object],
    session_factory: async_sessionmaker[AsyncSession],
    length: int,
) -> None:
    headers = {"Idempotency-Key": "x" * length}
    response = await client.post("/payments", json=payment_body, headers=headers)
    if length != 255:
        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["header", "Idempotency-Key"]
        assert await row_count(session_factory) == 0
        return

    assert response.status_code == 201
    repeated = await client.post("/payments", json=payment_body, headers=headers)
    assert repeated.status_code == 200
    assert repeated.json() == response.json()
    async with session_factory() as session:
        saved = await session.get(Payment, UUID(response.json()["id"]))
        assert saved.idempotency_key == headers["Idempotency-Key"]
    assert await row_count(session_factory) == 1


async def test_concurrent_idempotency(
    client: AsyncClient,
    payment_body: dict[str, object],
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    barrier = asyncio.Barrier(8)
    prechecked: set[AsyncSession] = set()
    insert_results: list[bool] = []
    original_scalar = AsyncSession.scalar

    async def synchronized_scalar(session, statement, *args, **kwargs):
        result = await original_scalar(session, statement, *args, **kwargs)
        if (
            getattr(statement, "is_select", False)
            and "payments.idempotency_key =" in str(statement)
            and session not in prechecked
        ):
            prechecked.add(session)
            assert result is None
            # All requests must miss the pre-check before any can INSERT.
            await barrier.wait()
        if (
            getattr(statement, "is_insert", False)
            and statement.table.name == "payments"
        ):
            insert_results.append(result is not None)
        return result

    monkeypatch.setattr(AsyncSession, "scalar", synchronized_scalar)
    responses = await asyncio.wait_for(
        asyncio.gather(
            *[
                client.post(
                    "/payments", json=payment_body, headers={"Idempotency-Key": "race"}
                )
                for _ in range(8)
            ]
        ),
        timeout=20,
    )
    assert sorted(response.status_code for response in responses) == [200] * 7 + [201]
    assert all(response.json() == responses[0].json() for response in responses)
    assert len(insert_results) == 8
    assert sum(insert_results) == 1
    assert await row_count(session_factory) == 1


async def test_database_enforces_unique_key(
    client: AsyncClient,
    payment_body: dict[str, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    response = await client.post(
        "/payments", json=payment_body, headers={"Idempotency-Key": "unique"}
    )
    assert response.status_code == 201
    with pytest.raises(IntegrityError):
        async with session_factory() as session, session.begin():
            session.add(
                Payment(
                    tariff_id=payment_body["tariff_id"],
                    email="other@example.com",
                    method="card",
                    amount=1990000,
                    discount=0,
                    idempotency_key="unique",
                )
            )
    assert await row_count(session_factory) == 1


async def test_requests_without_key_create_distinct_payments(
    client: AsyncClient,
    payment_body: dict[str, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    first = await client.post("/payments", json=payment_body)
    second = await client.post("/payments", json=payment_body)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert await row_count(session_factory) == 2


async def test_retrieve_payment(
    client: AsyncClient, payment_body: dict[str, object]
) -> None:
    created = await client.post("/payments", json=payment_body)
    response = await client.get(f"/payments/{created.json()['id']}")
    assert response.status_code == 200
    assert response.json() == created.json()
    missing = await client.get(f"/payments/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "payment_not_found"}
    assert (await client.get("/payments/not-a-uuid")).status_code == 422


async def test_list_filters_and_deterministic_order(
    client: AsyncClient,
    payment_body: dict[str, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    assert (await client.get("/payments")).json() == []
    payments = []
    for email in ["student@example.com", "other@example.com", "student@example.com"]:
        response = await client.post("/payments", json={**payment_body, "email": email})
        assert response.status_code == 201
        payments.append(response.json())
    # A tied timestamp checks the ID tiebreaker, independently of insertion order.
    async with session_factory() as session, session.begin():
        await session.execute(
            update(Payment).values(
                created_at=datetime.fromisoformat(payments[0]["created_at"])
            )
        )
        await session.execute(
            update(Payment)
            .where(Payment.id == UUID(payments[0]["id"]))
            .values(status="succeeded")
        )
    all_payments = (await client.get("/payments")).json()
    assert [p["id"] for p in all_payments] == sorted(p["id"] for p in payments)
    assert (await client.get("/payments")).json() == all_payments
    email = (
        await client.get("/payments", params={"email": "student@example.com"})
    ).json()
    assert {p["id"] for p in email} == {payments[0]["id"], payments[2]["id"]}
    status = (await client.get("/payments", params={"status": "pending"})).json()
    assert {p["id"] for p in status} == {payments[1]["id"], payments[2]["id"]}
    combined = (
        await client.get(
            "/payments",
            params={
                "email": "student@example.com",
                "status": "succeeded",
            },
        )
    ).json()
    assert len(combined) == 1
    assert combined[0]["id"] == payments[0]["id"]
    assert (
        await client.get("/payments", params={"email": "nobody@example.com"})
    ).json() == []
    assert (
        await client.get("/payments", params={"status": "invalid"})
    ).status_code == 422
