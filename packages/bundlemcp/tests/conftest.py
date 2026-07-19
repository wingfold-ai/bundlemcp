"""Hermetic test fixtures (ARC-14): in-memory sqlite + fakeredis, no network/Docker."""

from collections.abc import AsyncIterator

import pytest
from bundlemcp.store import create_all, create_engine, session_factory
from fakeredis.aioredis import FakeRedis
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_engine("sqlite+aiosqlite://")

    # sqlite needs FKs switched on for the ondelete=CASCADE behavior (DOM-2)
    @event.listens_for(eng.sync_engine, "connect")
    def _fk_on(dbapi_conn, _record):  # pragma: no cover - trivial
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    await create_all(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
async def db(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = session_factory(engine)
    async with factory() as session:
        yield session


@pytest.fixture
async def redis() -> AsyncIterator[FakeRedis]:
    r = FakeRedis(decode_responses=True)
    yield r
    await r.flushall()
    await r.aclose()
