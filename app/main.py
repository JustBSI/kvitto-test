"""Application factory; each instance owns its engine and session factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import router
from app.config import Settings
from app.database import seed_tariffs


def create_app(settings: Settings | None = None) -> FastAPI:
    """Validate configuration and create an independent application instance."""
    if settings is None:
        settings = Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        engine = create_async_engine(
            settings.database_url.get_secret_value(), hide_parameters=True
        )
        application.state.engine = engine
        application.state.session_factory = async_sessionmaker(
            engine, expire_on_commit=False
        )
        try:
            async with application.state.session_factory() as session:
                async with session.begin():
                    await seed_tariffs(session)
            yield
        finally:
            await engine.dispose()

    application = FastAPI(
        title="Kvitto Payment API", version="0.1.0", lifespan=lifespan
    )
    application.state.settings = settings
    application.include_router(router)
    return application
