import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.database import seed_tariffs
from app.main import create_app
from app.models import Tariff

pytestmark = pytest.mark.asyncio


async def test_startup_seeds_tariffs_and_is_idempotent(
    test_settings: Settings,
    database_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with database_session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Tariff)) == 0

    app = create_app(test_settings)
    responses = []
    for _ in range(2):
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/tariffs")
            assert response.status_code == 200
            tariffs = response.json()
            assert [(item["title"], item["price"]) for item in tariffs] == [
                ("basic", 990000),
                ("standard", 1990000),
                ("premium", 2990000),
            ]
            responses.append(tariffs)

    assert responses[0] == responses[1]
    async with database_session_factory() as session:
        stored = (
            await session.execute(
                select(Tariff.id, Tariff.title, Tariff.price).order_by(Tariff.price)
            )
        ).all()
    assert stored == [
        (item["id"], item["title"], item["price"]) for item in responses[0]
    ]


async def test_startup_restores_missing_tariff(
    test_settings: Settings,
    database_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    app = create_app(test_settings)
    async with app.router.lifespan_context(app):
        async with database_session_factory() as session:
            original = (await session.execute(select(Tariff))).scalars().all()
            original_by_title = {
                tariff.title: (tariff.id, tariff.price) for tariff in original
            }
    assert set(original_by_title) == {"basic", "standard", "premium"}

    async with database_session_factory() as session, session.begin():
        await session.execute(delete(Tariff).where(Tariff.title == "basic"))
    async with database_session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Tariff)) == 2

    async with app.router.lifespan_context(app):
        async with database_session_factory() as session:
            restored = (await session.execute(select(Tariff))).scalars().all()
            restored_by_title = {
                tariff.title: (tariff.id, tariff.price) for tariff in restored
            }

    assert {title: price for title, (_, price) in restored_by_title.items()} == {
        "basic": 990000,
        "standard": 1990000,
        "premium": 2990000,
    }
    for title in ["standard", "premium"]:
        assert restored_by_title[title] == original_by_title[title]


async def test_concurrent_seed_from_empty_database(
    database_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with database_session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Tariff)) == 0

    async def seed() -> None:
        async with database_session_factory() as session, session.begin():
            await seed_tariffs(session)

    await asyncio.wait_for(asyncio.gather(seed(), seed(), seed()), timeout=10)

    async with database_session_factory() as session:
        actual = (
            await session.execute(
                select(Tariff.title, Tariff.price).order_by(Tariff.price)
            )
        ).all()
    assert actual == [("basic", 990000), ("standard", 1990000), ("premium", 2990000)]


async def test_tariffs(client: AsyncClient) -> None:
    response = await client.get("/tariffs")

    assert response.status_code == 200
    tariffs = response.json()
    assert [(item["title"], item["price"]) for item in tariffs] == [
        ("basic", 990000),
        ("standard", 1990000),
        ("premium", 2990000),
    ]
    assert all(isinstance(item["id"], int) for item in tariffs)


async def test_seed_is_idempotent_and_concurrency_safe(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def seed() -> None:
        async with session_factory() as session, session.begin():
            await seed_tariffs(session)

    async with session_factory() as session:
        original = (await session.execute(select(Tariff.id, Tariff.price))).all()

    await asyncio.gather(seed(), seed(), seed())

    async with session_factory() as session:
        actual = (await session.execute(select(Tariff.id, Tariff.price))).all()
        count = await session.scalar(select(func.count()).select_from(Tariff))

    assert count == 3
    assert sorted(actual) == sorted(original)
