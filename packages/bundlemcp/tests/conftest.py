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


# Mid-window for every window length the suite uses, so no test starts within
# rounding distance of a bucket boundary.
FIXED_CLOCK_SECONDS = 1_700_000_050


class ClockedFakeRedis(FakeRedis):
    """FakeRedis whose ``TIME`` is fixed rather than the wall clock.

    The rate limiter derives its fixed-window bucket from server time, so a
    suite running on the wall clock straddles a window boundary every so often
    and a counting assertion fails for reasons that have nothing to do with the
    code under test. Freezing the clock makes those tests deterministic; a test
    that wants a rollover asks for one with ``advance``.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._clock_seconds = FIXED_CLOCK_SECONDS

    async def time(self) -> tuple[int, int]:
        return self._clock_seconds, 0

    def advance(self, seconds: int) -> None:
        """Move the shared clock forward, e.g. past a rate-limit window edge."""
        self._clock_seconds += seconds


@pytest.fixture
async def redis() -> AsyncIterator[ClockedFakeRedis]:
    r = ClockedFakeRedis(decode_responses=True)
    yield r
    await r.flushall()
    await r.aclose()
