"""Concurrent discoveries of one server on the in-memory fakes."""

import asyncio
import uuid

import pytest
from bundlemcp.application.contracts.upstream.upstream_probe import ProbeResult
from bundlemcp.application.discovery.discovery_service import DiscoveryService
from bundlemcp.application.management.server_service import ServerService
from bundlemcp.application.schemas import ServerUpsert
from bundlemcp.domain.servers.probed_tool import ProbedTool
from bundlemcp.domain.shared.system_clock import SystemClock
from bundlemcp.infrastructure.memory.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
    InMemoryUnitOfWorkFactory,
)
from bundlemcp.infrastructure.memory.noop_tool_discovery import NoopToolDiscovery

from tests.application.upstream_health_on_fakes import health_on

# how long a probe waits for a second one to start before it answers anyway
OVERLAP_WINDOW_SECONDS = 0.3


class OverlappingProbe:
    """Lists the same tools every time, holding each answer until a second probe has
    started or a short window closes, and records how many probes of one server
    were ever in flight at once."""

    def __init__(self, *names: str) -> None:
        self.names = list(names)
        self.in_flight = 0
        self.most_in_flight = 0
        self._started = 0
        self._second = asyncio.Event()

    async def probe(self, server, headers) -> ProbeResult:
        self._started += 1
        self.in_flight += 1
        self.most_in_flight = max(self.most_in_flight, self.in_flight)
        if self._started >= 2:
            self._second.set()
        try:
            await asyncio.wait_for(self._second.wait(), OVERLAP_WINDOW_SECONDS)
        except TimeoutError:
            pass
        finally:
            self.in_flight -= 1
        return ProbeResult(
            tools=[ProbedTool(name=n) for n in self.names], capabilities=None, protocol_version=None
        )


class StalledProbe:
    """Never answers for the server whose URL it stalls on; lists one tool for any other."""

    def __init__(self, stalled_url: str) -> None:
        self.stalled_url = stalled_url
        self.stalling = asyncio.Event()

    async def probe(self, server, headers) -> ProbeResult:
        if server.url == self.stalled_url:
            self.stalling.set()
            await asyncio.Event().wait()
        return ProbeResult(
            tools=[ProbedTool(name="alpha")], capabilities=None, protocol_version=None
        )


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


async def _registered(uow: InMemoryUnitOfWork, name: str) -> uuid.UUID:
    server = await ServerService(
        uow, discovery=NoopToolDiscovery(), public_base="http://gw"
    ).upsert(ServerUpsert(name=name, url=f"http://{name}/mcp"))
    return server.id


def _discovery(uow: InMemoryUnitOfWork, probe) -> DiscoveryService:
    return DiscoveryService(
        InMemoryUnitOfWorkFactory(uow), probe, health=health_on(uow), clock=SystemClock()
    )


async def test_ups39_concurrent_discoveries_store_each_tool_once(uow):
    """UPS-39: two discoveries of one server started together run one after the other,
    so each tool is stored once and the second reports no change."""
    server_id = await _registered(uow, "echo")
    probe = OverlappingProbe("alpha", "beta")
    discovery = _discovery(uow, probe)

    first, second = await asyncio.gather(
        discovery.discover(server_id), discovery.discover(server_id)
    )

    assert probe.most_in_flight == 1
    assert first.error is None and second.error is None
    assert sorted(t.name for t in await uow.tools.for_server(server_id)) == ["alpha", "beta"]
    assert sorted([first.changed, second.changed]) == [0, 2]


async def test_ups39_a_stalled_discovery_does_not_hold_up_another_server(uow):
    """UPS-39: a discovery waiting on one server's probe does not delay another server's."""
    stalled = await _registered(uow, "slow")
    other = await _registered(uow, "fast")
    probe = StalledProbe("http://slow/mcp")
    discovery = _discovery(uow, probe)

    waiting = asyncio.create_task(discovery.discover(stalled))
    await probe.stalling.wait()
    try:
        result = await asyncio.wait_for(discovery.discover(other), 1)
    finally:
        waiting.cancel()

    assert result.error is None
    assert [t.name for t in await uow.tools.for_server(other)] == ["alpha"]


class HeldProbe:
    """Holds every probe until released, then lists one tool."""

    def __init__(self) -> None:
        self.probing = asyncio.Event()
        self.release = asyncio.Event()

    async def probe(self, server, headers) -> ProbeResult:
        self.probing.set()
        await self.release.wait()
        return ProbeResult(
            tools=[ProbedTool(name="alpha")], capabilities=None, protocol_version=None
        )


async def _delete(units: InMemoryUnitOfWorkFactory, name: str) -> None:
    async with units.open() as uow:
        await ServerService(uow, discovery=NoopToolDiscovery(), public_base="http://gw").delete(
            name
        )


async def test_ups40_a_delete_waits_for_a_running_discovery_and_the_server_stays_deleted(uow):
    """UPS-40: a delete that arrives while a discovery of the server probes waits for it to
    finish, and the server is gone afterwards instead of being stored again by the discovery."""
    server_id = await _registered(uow, "echo")
    probe = HeldProbe()
    units = InMemoryUnitOfWorkFactory(uow)
    discovery = DiscoveryService(units, probe, health=health_on(uow), clock=SystemClock())

    discovering = asyncio.create_task(discovery.discover(server_id))
    await probe.probing.wait()
    deleting = asyncio.create_task(_delete(units, "echo"))
    await asyncio.sleep(0.05)
    waited = not deleting.done()
    probe.release.set()
    result = await discovering
    await deleting

    assert waited
    assert result.error is None
    assert await uow.servers.get(server_id) is None
    assert await uow.servers.by_name("echo") is None


async def test_ups40_a_server_removed_under_a_running_discovery_stays_removed(uow):
    """UPS-40: a server removed without waiting for the lock while its discovery probes is
    not stored again, and the discovery stores no tool for it."""
    server_id = await _registered(uow, "echo")
    probe = HeldProbe()
    discovery = _discovery(uow, probe)

    discovering = asyncio.create_task(discovery.discover(server_id))
    await probe.probing.wait()
    await uow.servers.delete(await uow.servers.get(server_id))
    probe.release.set()
    result = await discovering

    assert result.error == "server not found"
    assert await uow.servers.get(server_id) is None
    assert await uow.tools.for_server(server_id) == []
