"""Alembic uses the same async PostgreSQL driver as the application."""

import asyncio
from logging.config import fileConfig

from alembic import context
from pydantic import SecretStr
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import Settings
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    # Tests explicitly supply their isolated database; normal migrations use Settings.
    override = config.attributes.get("database_url")
    if override is not None:
        return Settings.validate_database_url(SecretStr(override)).get_secret_value()
    return Settings().database_url.get_secret_value()


def run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    engine = create_async_engine(
        database_url(), poolclass=pool.NullPool, hide_parameters=True
    )
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_online())
