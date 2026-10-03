"""Engine lifecycle, one session per request, and idempotent tariff initialization."""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Tariff

TARIFFS = (
    {"title": "basic", "price": 990000},
    {"title": "standard", "price": 1990000},
    {"title": "premium", "price": 2990000},
)


async def seed_tariffs(session: AsyncSession) -> None:
    """The caller owns the transaction; concurrent startups cannot add duplicates."""
    statement = (
        insert(Tariff)
        .values(list(TARIFFS))
        .on_conflict_do_nothing(constraint="uq_tariffs_title")
    )
    await session.execute(statement)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Close the session (including read transactions) after each request."""
    async with request.app.state.session_factory() as session:
        yield session
