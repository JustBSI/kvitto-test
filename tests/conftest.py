"""Integration tests use an explicitly configured, disposable PostgreSQL database."""

import os
import secrets
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings
from app.main import create_app
from app.models import Payment, Tariff


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    url = os.environ.get("TEST_DATABASE_URL")
    if url is None:
        pytest.fail("Set TEST_DATABASE_URL to a dedicated PostgreSQL *_test database")
    parsed_url = make_url(url)
    if not parsed_url.database or not parsed_url.database.endswith("_test"):
        pytest.fail("Tests refuse to clean a database whose name does not end in _test")
    return Settings(
        _env_file=None, database_url=url, webhook_secret=secrets.token_hex(32)
    )


@pytest.fixture(scope="session")
def migrated_database(test_settings: Settings) -> None:
    config = Config("alembic.ini")
    config.attributes["database_url"] = test_settings.database_url.get_secret_value()
    command.upgrade(config, "head")


@pytest_asyncio.fixture
async def database_session_factory(
    test_settings: Settings, migrated_database: None
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    # Clean before startup, but never seed: initialization must come from lifespan.
    engine = create_async_engine(
        test_settings.database_url.get_secret_value(), hide_parameters=True
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session, session.begin():
            await session.execute(delete(Payment))
            await session.execute(delete(Tariff))
        yield factory
    finally:
        try:
            async with factory() as session, session.begin():
                await session.execute(delete(Payment))
                await session.execute(delete(Tariff))
        finally:
            await engine.dispose()


@pytest_asyncio.fixture
async def application(
    test_settings: Settings,
    database_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[FastAPI]:
    app = create_app(test_settings)
    # HTTPX's ASGITransport does not run ASGI lifespan automatically.
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
def session_factory(application: FastAPI) -> async_sessionmaker[AsyncSession]:
    return application.state.session_factory


@pytest.fixture
def engine(application: FastAPI) -> AsyncEngine:
    return application.state.engine


@pytest_asyncio.fixture
async def client(application: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        yield client
