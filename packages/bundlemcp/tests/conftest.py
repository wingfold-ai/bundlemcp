"""Hermetic test fixtures (ARC-14): in-memory sqlite + fakeredis, no network/Docker.

``serving`` is the one place the app is composed for a test: settings,
overrides, the ASGI client and the lifespan. A suite that needs a variation
passes it in rather than copying the wiring.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from bundlemcp.application.settings.settings import Settings
from bundlemcp.domain.access.api_key import ApiKey
from bundlemcp.domain.access.api_key_kind import ApiKeyKind
from bundlemcp.domain.shared.secrets import (
    API_KEY_PREFIX,
    display_prefix,
    generate_token,
    hash_token,
)
from bundlemcp.infrastructure.config.settings import EnvSettings
from bundlemcp.infrastructure.postgres.engine import create_all, create_engine, session_factory
from bundlemcp.infrastructure.postgres.rows.api_key_row import ApiKeyRow
from bundlemcp.infrastructure.postgres.shipped_migrations import ShippedMigrations
from bundlemcp.main.app import create_app
from bundlemcp.main.composition_overrides import CompositionOverrides
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

SERVICE_KEY = generate_token(API_KEY_PREFIX)
ENDPOINT_KEY = generate_token(API_KEY_PREFIX)


async def background_probes_done() -> None:
    """Wait for every discovery probe running in the background to finish.

    Tests await the probe instead of polling for its result: the hermetic sqlite
    database is one shared connection, so a read made while a probe is writing
    sees its uncommitted rows and then ends the probe's transaction with its own.
    """
    probes = [
        task
        for task in asyncio.all_tasks()
        if task.get_coro().__qualname__.endswith("._probe_quietly")  # type: ignore[union-attr]
    ]
    await asyncio.gather(*probes)


def hermetic_settings(**extra: Any) -> Settings:
    """Settings for an in-process app: no env file, the shared in-memory database."""
    return EnvSettings(_env_file=None, database_url="sqlite+aiosqlite://", **extra)


async def seed_api_key(
    engine: AsyncEngine, key: str, *, name: str = "svc", kind: ApiKeyKind = ApiKeyKind.SERVICE
) -> ApiKey:
    """Store one API key so requests carrying it authenticate."""
    async with session_factory(engine)() as db:
        row = ApiKeyRow(
            name=name, key_hash=hash_token(key), key_prefix=display_prefix(key), kind=kind
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return ApiKey.model_validate(row, from_attributes=True)


@asynccontextmanager
async def serving(
    engine: AsyncEngine,
    redis: FakeRedis,
    *,
    settings: Settings | None = None,
    base_url: str = "http://gw",
    bearer: str | None = None,
    follow_redirects: bool = True,
    **overrides: Any,
) -> AsyncIterator[tuple[AsyncClient, FastAPI]]:
    """The composed app inside its lifespan, and an ASGI client talking to it.

    ``overrides`` are the ``CompositionOverrides`` fields beyond the engine and
    the Valkey client, which every hermetic app receives from the fixtures.
    """
    app = create_app(
        settings or hermetic_settings(),
        overrides=CompositionOverrides(engine=engine, redis=redis, **overrides),
    )
    headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url=base_url,
        headers=headers,
        follow_redirects=follow_redirects,
    ) as http:
        async with app.router.lifespan_context(app):
            yield http, app


@pytest.fixture
async def service_client(engine: AsyncEngine, redis: FakeRedis) -> AsyncIterator[AsyncClient]:
    """A management-API client authenticated with a seeded service key."""
    await seed_api_key(engine, SERVICE_KEY)
    async with serving(engine, redis, bearer=SERVICE_KEY) as (http, _app):
        yield http


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_engine("sqlite+aiosqlite://")

    # sqlite needs FKs switched on for the ondelete=CASCADE behavior
    @event.listens_for(eng.sync_engine, "connect")
    def _fk_on(dbapi_conn, _record):  # pragma: no cover - trivial
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    await create_all(eng)
    await stamp_head(eng)
    yield eng
    await eng.dispose()


async def stamp_head(eng: AsyncEngine, revision: str | None = None) -> None:
    """Record a migration revision, the shipped head by default: create_all builds the head's
    schema without Alembic, and readiness checks the revision."""
    applied = revision or ShippedMigrations.read().head
    async with eng.begin() as conn:
        await conn.execute(
            text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)")
        )
        await conn.execute(text("DELETE FROM alembic_version"))
        await conn.execute(text("INSERT INTO alembic_version VALUES (:v)"), {"v": applied})


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
