"""Fixtures for tests that need Postgres (docker compose up -d).

They use a separate `*_test` database. Locally they are skipped if Postgres is down;
in CI (the CI env var is set) they fail instead, so they can never be skipped silently.
"""

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import make_url, pool, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_TEST_DATABASE_URL = "postgresql+asyncpg://lumen:lumen@localhost:5433/lumen_test"


class IntegrationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    test_database_url: str = DEFAULT_TEST_DATABASE_URL


def alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["database_url"] = database_url
    config.attributes["configure_logger"] = False
    return config


async def _connection_error(database_url: str) -> str | None:
    """None if the database answers, otherwise why it doesn't."""
    engine = create_async_engine(database_url, poolclass=pool.NullPool)
    try:
        async with asyncio.timeout(3), engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except (OSError, TimeoutError, SQLAlchemyError) as error:
        name, detail = type(error).__name__, str(error)
        return f"{name}: {detail}" if detail else name
    finally:
        await engine.dispose()
    return None


@pytest.fixture(scope="session")
def database_url() -> str:
    url = IntegrationSettings().test_database_url
    parsed = make_url(url)
    if not (parsed.database or "").endswith("_test"):
        shown = parsed.render_as_string(hide_password=True)
        pytest.fail(
            f"TEST_DATABASE_URL must name a *_test database (tests drop its tables): {shown}"
        )
    error = asyncio.run(_connection_error(url))
    if error:
        message = f"Postgres test database not reachable ({error}). Run: docker compose up -d"
        if os.environ.get("CI"):
            pytest.fail(message)
        pytest.skip(message)
    return url


@pytest.fixture(scope="session")
def migrated_database_url(database_url: str) -> str:
    """Rebuild the schema from the migrations once per test run."""
    config = alembic_config(database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    return database_url


@pytest.fixture
async def db_session(migrated_database_url: str) -> AsyncIterator[AsyncSession]:
    """A session whose work is rolled back after each test, even if the code commits."""
    engine = create_async_engine(migrated_database_url, poolclass=pool.NullPool)
    async with engine.connect() as conn:
        transaction = await conn.begin()
        session = AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()
