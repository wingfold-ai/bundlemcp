"""Providers for the collaborators the composition root publishes.

Each ``get_*`` reads one field off the app's container; the ``*Provider``
alias injects it into a route signature. ``get_unit_of_work`` is the exception
that opens a request-scoped unit of work rather than handing out a shared object.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bundlemcp.settings import Settings
from bundlemcp.store import UnitOfWork, UnitOfWorkFactory


async def get_unit_of_work(request: Request) -> AsyncIterator[UnitOfWork]:
    factory: UnitOfWorkFactory = request.app.state.container.unit_of_work_factory
    async with factory.open() as uow:
        yield uow


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    """The factory itself, for handlers that deliberately open more than one transaction."""
    return request.app.state.container.session_factory


def get_redis(request: Request) -> Redis:
    return request.app.state.container.redis


def get_app_settings(request: Request) -> Settings:
    return request.app.state.container.settings


UnitOfWorkProvider = Annotated[UnitOfWork, Depends(get_unit_of_work)]
SessionFactoryProvider = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
RedisProvider = Annotated[Redis, Depends(get_redis)]
SettingsProvider = Annotated[Settings, Depends(get_app_settings)]
