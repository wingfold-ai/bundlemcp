"""Providers for the process-wide collaborators the composition root publishes.

Each ``get_*`` reads one object off ``app.state``; the ``*Provider`` alias
injects it into a route signature. ``get_db`` is the exception that yields a
new request-scoped session rather than a shared object.
"""

from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bundlemcp.settings import Settings


async def get_db(request: Request) -> AsyncSession:
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    """The factory itself, for handlers that need several short transactions.

    Prefer ``DbProvider`` for a single request-scoped session; take the factory
    only when the handler deliberately opens and commits more than one.
    """
    return request.app.state.session_factory


async def get_redis(request: Request) -> Redis:
    return request.app.state.redis


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


DbProvider = Annotated[AsyncSession, Depends(get_db)]
SessionFactoryProvider = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
RedisProvider = Annotated[Redis, Depends(get_redis)]
SettingsProvider = Annotated[Settings, Depends(get_app_settings)]
