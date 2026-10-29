"""Idle sessions are swept on one replica at a time (SES-10)."""

import uuid
from datetime import UTC, datetime, timedelta

from bundlemcp.api.jobs.session_sweep_job import SessionSweepJob
from bundlemcp.application.contracts.live_state.resource_subscriptions import (
    ResourceSubscription,
)
from bundlemcp.application.serving.runtime_config import RuntimeConfig
from bundlemcp.application.sessions.expired_session_release import ExpiredSessionRelease
from bundlemcp.application.sessions.session_sweeper import SessionSweeper
from bundlemcp.domain.access.caller_identity import CallerIdentity
from bundlemcp.domain.config.config_entry import ConfigEntry
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.sessions.session_lifetime import SessionLifetime
from bundlemcp.domain.sessions.session_record import SessionRecord
from bundlemcp.domain.sessions.upstream_binding import UpstreamBinding
from bundlemcp.domain.shared.system_clock import SystemClock
from bundlemcp.infrastructure.memory.in_memory_unit_of_work import InMemoryUnitOfWorkFactory
from bundlemcp.infrastructure.memory.manual_clock import ManualClock
from bundlemcp.infrastructure.valkey.refresh_lock import ValkeyRefreshLock
from bundlemcp.infrastructure.valkey.resource_subscription_index import (
    ValkeyResourceSubscriptionIndex,
)
from bundlemcp.infrastructure.valkey.session_store import ValkeySessionStore
from structlog.testing import capture_logs

NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)
HOUR = SessionLifetime(seconds=3600)


def _record(session_id: str, idle: timedelta) -> SessionRecord:
    return SessionRecord(
        session_id=session_id,
        endpoint_name="main",
        bundle_name="demo",
        identity=CallerIdentity.with_api_key(uuid.uuid4()),
        protocol_version="2025-11-25",
        last_active_at=NOW - idle,
    )


def _config(lifetime: int) -> RuntimeConfig:
    units = InMemoryUnitOfWorkFactory()
    units.uow.config_entries.add(ConfigEntry(key="session_lifetime", value=lifetime))
    return RuntimeConfig(units)


async def test_ses10_an_idle_session_is_removed_and_counted(redis):
    """SES-10: a session idle past the lifetime is removed, and the expiry is logged."""
    store = ValkeySessionStore(redis, clock=SystemClock())
    await store.create(_record("idle", timedelta(hours=2)), HOUR)
    await store.create(_record("busy", timedelta(minutes=5)), HOUR)
    sweeper = SessionSweeper(store, _config(3600), ManualClock(NOW), _nothing_held)
    with capture_logs() as logs:
        assert await sweeper.sweep() == 1
    assert await store.load("idle") is None
    assert await store.load("busy") is not None
    assert [entry["event"] for entry in logs] == ["session.expired"]


async def test_ses10_touch_and_sweep_read_one_clock(redis):
    """SES-10: activity is stamped by the same clock the sweeper reads, so a touched session is
    not idle until that clock passes the lifetime, and is idle one second after."""
    clock = ManualClock(NOW)
    store = ValkeySessionStore(redis, clock=clock)
    await store.create(_record("s1", timedelta(hours=2)), HOUR)
    await store.touch("s1", HOUR)
    sweeper = SessionSweeper(store, _config(3600), clock, _nothing_held)

    clock.advance(timedelta(seconds=3599))
    assert await sweeper.sweep() == 0
    assert await store.load("s1") is not None

    clock.advance(timedelta(seconds=2))
    assert await sweeper.sweep() == 1
    assert await store.load("s1") is None


async def test_ses10_a_session_active_again_since_it_was_indexed_survives(redis):
    """SES-10: the record, not the index, decides; a fresh activity time keeps the session."""
    store = ValkeySessionStore(redis, clock=SystemClock())
    record = _record("back", timedelta(hours=2))
    await store.create(record, HOUR)
    record.last_active_at = NOW  # touched meanwhile, index not yet updated
    await redis.set("bmcp:session:back", record.model_dump_json())
    assert await SessionSweeper(store, _config(3600), ManualClock(NOW), _nothing_held).sweep() == 0
    assert await store.load("back") is not None


async def test_ses10_an_id_whose_record_is_gone_leaves_the_index(redis):
    """SES-10: the TTL removed the record first; the sweeper only tidies the index."""
    store = ValkeySessionStore(redis, clock=SystemClock())
    await store.create(_record("gone", timedelta(hours=2)), HOUR)
    await redis.delete("bmcp:session:gone")
    assert await SessionSweeper(store, _config(3600), ManualClock(NOW), _nothing_held).sweep() == 0
    assert await redis.zscore("bmcp:sessions:active", "gone") is None


async def test_ses10_no_idle_expiry_sweeps_nothing(redis):
    """SES-10: with session_lifetime 0 nothing is ever swept."""
    store = ValkeySessionStore(redis, clock=SystemClock())
    await store.create(_record("old", timedelta(days=3)), HOUR)
    assert await SessionSweeper(store, _config(0), ManualClock(NOW), _nothing_held).sweep() == 0
    assert await store.load("old") is not None


async def test_ses10_only_one_replica_sweeps(redis):
    """SES-10: two jobs reach the same tick; the lease lets one of them sweep."""
    store = ValkeySessionStore(redis, clock=SystemClock())
    await store.create(_record("idle", timedelta(hours=2)), HOUR)

    def job() -> SessionSweepJob:
        sweeper = SessionSweeper(store, _config(3600), ManualClock(NOW), _nothing_held)
        return SessionSweepJob(sweeper, ValkeyRefreshLock(redis))

    results = [await job().sweep_once(), await job().sweep_once()]
    assert results == [1, None]


async def _nothing_held(record) -> None:
    return None


async def test_ses10_an_expired_session_releases_its_upstream_sessions(redis):
    """SES-10, SES-4: the sweeper ends what an expired session held upstream, and only that."""
    store = ValkeySessionStore(redis, clock=SystemClock())
    await store.create(_record("idle", timedelta(hours=2)), HOUR)
    await store.create(_record("busy", timedelta(minutes=5)), HOUR)
    released: list[str] = []

    async def release(record: SessionRecord) -> None:
        released.append(record.session_id)

    assert await SessionSweeper(store, _config(3600), ManualClock(NOW), release).sweep() == 1
    assert released == ["idle"]


async def test_ses4_release_ends_bound_upstream_sessions_and_subscriptions(redis):
    """SES-4: each binding with an upstream session is ended; its subscriptions are dropped."""
    units = InMemoryUnitOfWorkFactory()
    units.uow.servers.add(McpServer(name="echo", url="https://echo.example/mcp"))
    subscriptions = ValkeyResourceSubscriptionIndex(redis)
    subscription = ResourceSubscription(server_name="echo", uri="file:///report")
    await subscriptions.subscribe("idle", subscription)
    ended: list[tuple[str, str | None]] = []

    class Pool:
        async def end(self, server, binding, headers):
            ended.append((server.name, binding.upstream_session_id))

    record = _record("idle", timedelta(hours=2))
    record.bindings = {
        "echo": UpstreamBinding(server_name="echo", upstream_session_id="up-1"),
        "gone": UpstreamBinding(server_name="gone", upstream_session_id="up-2"),
        "fresh": UpstreamBinding(server_name="echo"),
    }
    await ExpiredSessionRelease(units, Pool(), subscriptions)(record)
    assert ended == [("echo", "up-1")]
    assert await subscriptions.streams(subscription) == []
