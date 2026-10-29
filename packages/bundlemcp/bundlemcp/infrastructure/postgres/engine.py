"""Async engine/session plumbing. Schema changes ship as Alembic migrations."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel import SQLModel

import bundlemcp.infrastructure.postgres.rows  # noqa: F401  (register every table on the metadata)


def create_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    """An engine whose errors and echo name the statement but never its bound parameters,
    which can hold ciphertexts, token hashes and other values that must stay out of logs."""
    return create_async_engine(database_url, echo=echo, pool_pre_ping=True, hide_parameters=True)


def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def create_all(engine: AsyncEngine) -> None:
    """Create the full schema directly — tests and dev only; production uses Alembic."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
