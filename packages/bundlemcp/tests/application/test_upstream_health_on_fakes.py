"""Upstream health from a failure streak every replica shares (UPS-4, UPS-23)."""

from bundlemcp.application.discovery.discovery_service import DiscoveryService
from bundlemcp.domain.config.config_entry import ConfigEntry
from bundlemcp.domain.servers.connection_state import ConnectionState
from bundlemcp.domain.servers.health_status import HealthStatus
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.probe_failure import ProbeFailure
from bundlemcp.infrastructure.memory.in_memory_failure_streak import InMemoryFailureStreak
from bundlemcp.infrastructure.memory.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
    InMemoryUnitOfWorkFactory,
)

from tests.application.upstream_health_on_fakes import health_on


class DownProbe:
    """An upstream that never answers."""

    async def probe(self, server, headers):
        raise ProbeFailure("connection refused", state=ConnectionState.UNREACHABLE)


def _seeded() -> tuple[InMemoryUnitOfWork, McpServer]:
    uow = InMemoryUnitOfWork()
    server = McpServer(name="down", url="http://down/mcp")
    uow.servers.add(server)
    return uow, server


async def _status(uow: InMemoryUnitOfWork, server: McpServer) -> HealthStatus:
    stored = await uow.servers.get(server.id)
    assert stored is not None
    return stored.health_status


async def test_ups4_threshold_from_runtime_config():
    """UPS-4: server_error_attempts sets how many failures in a row mark a server as failing."""
    uow, server = _seeded()
    uow.config_entries.add(ConfigEntry(key="server_error_attempts", value=5))
    health = health_on(uow)
    for _ in range(4):
        await health.failed(server.id, "connection refused")
    assert await _status(uow, server) != HealthStatus.ERROR
    await health.failed(server.id, "connection refused")
    stored = await uow.servers.get(server.id)
    assert stored is not None
    assert stored.health_status == HealthStatus.ERROR
    assert stored.last_error == "connection refused"


async def test_ups4_success_heals():
    """UPS-4: an answer from a failing server heals it and ends its streak."""
    uow, server = _seeded()
    streak = InMemoryFailureStreak()
    health = health_on(uow, streak)
    for _ in range(3):
        await health.failed(server.id, "connection refused")
    assert await _status(uow, server) == HealthStatus.ERROR
    await health.succeeded(server.id, HealthStatus.ERROR)
    stored = await uow.servers.get(server.id)
    assert stored is not None
    assert stored.health_status == HealthStatus.OK and stored.last_error is None
    assert server.id not in streak.streaks


async def test_ups4_a_healthy_server_s_success_touches_no_store():
    """UPS-4: a call to a healthy server only ends the streak; nothing is written."""
    uow, server = _seeded()
    streak = InMemoryFailureStreak()
    await streak.record_failure(server.id)
    await health_on(uow, streak).succeeded(server.id, HealthStatus.OK)
    assert server.id not in streak.streaks


async def test_ups4_failures_on_two_replicas_add_up():
    """UPS-4: two failed probes on one replica and a third on another mark the server."""
    uow, server = _seeded()
    streak = InMemoryFailureStreak()
    units = InMemoryUnitOfWorkFactory(uow)
    replica_a = DiscoveryService(units, DownProbe(), health=health_on(uow, streak))
    replica_b = DiscoveryService(units, DownProbe(), health=health_on(uow, streak))
    await replica_a.discover(server.id)
    await replica_a.discover(server.id)
    assert await _status(uow, server) != HealthStatus.ERROR
    await replica_b.discover(server.id)
    assert await _status(uow, server) == HealthStatus.ERROR


async def test_ups23_unreachable_upstream_marked_error_across_replicas():
    """UPS-23: three sweeps by different replicas mark an upstream that stays down."""
    uow, server = _seeded()
    streak = InMemoryFailureStreak()
    units = InMemoryUnitOfWorkFactory(uow)
    replicas = [
        DiscoveryService(units, DownProbe(), health=health_on(uow, streak)) for _ in range(2)
    ]
    for sweep in range(3):
        result = await replicas[sweep % 2].discover_all()
        assert result.failed == 1
    assert await _status(uow, server) == HealthStatus.ERROR


async def test_ups4_a_streak_store_outage_never_fails_a_probe():
    """UPS-4: counting is best effort; a probe still records what it found."""

    class BrokenStreak(InMemoryFailureStreak):
        async def record_failure(self, server_id):
            raise ConnectionError("valkey down")

    uow, server = _seeded()
    discovery = DiscoveryService(
        InMemoryUnitOfWorkFactory(uow), DownProbe(), health=health_on(uow, BrokenStreak())
    )
    result = await discovery.discover(server.id)
    assert result.connection_state == ConnectionState.UNREACHABLE
