"""Async engine and sessions.

The engine is created once in the FastAPI lifespan (app/main.py) and stored on
`app.state`. Creating it does not connect; the first query does.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(database_url: str) -> AsyncEngine:
    # pool_pre_ping drops connections the server closed (e.g. Neon suspending when idle).
    return create_async_engine(database_url, pool_pre_ping=True)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request."""
    async with request.app.state.sessionmaker() as session:
        yield session


SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


def get_session_factory(request: Request) -> SessionFactory:
    """For streaming routes, which open sessions while the response is being sent,
    after request-scoped dependencies like `get_db` may already be closed."""
    return request.app.state.sessionmaker


DbSession = Annotated[AsyncSession, Depends(get_db)]
Sessions = Annotated[SessionFactory, Depends(get_session_factory)]
