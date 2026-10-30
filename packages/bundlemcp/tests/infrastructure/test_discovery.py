"""Discovery tests (UPS-17/18/19, UPS-4) against in-process FastMCP servers."""

import asyncio
from datetime import UTC, datetime, timedelta

from bundlemcp.application.contracts.upstream.upstream_probe import ProbeResult
from bundlemcp.application.discovery.discovery_service import DiscoveryService
from bundlemcp.application.discovery.upstream_health import UpstreamHealth
from bundlemcp.application.management.server_service import ServerService
from bundlemcp.application.serving.runtime_config import RuntimeConfig
from bundlemcp.domain.servers.connection_state import ConnectionState
from bundlemcp.domain.servers.health_status import HealthStatus
from bundlemcp.domain.shared.clock import Clock
from bundlemcp.domain.shared.system_clock import SystemClock
from bundlemcp.infrastructure.fastmcp.connect_mode import connect_mode
from bundlemcp.infrastructure.fastmcp.upstream_probe import FastMcpUpstreamProbe
from bundlemcp.infrastructure.memory.manual_clock import ManualClock
from bundlemcp.infrastructure.memory.noop_tool_discovery import NoopToolDiscovery
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.postgres.rows.tool_row import ToolRow
from bundlemcp.infrastructure.postgres.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWorkFactory
from bundlemcp.infrastructure.valkey.failure_streak_store import ValkeyFailureStreak
from fastmcp import Client, FastMCP
from sqlmodel import select


def make_upstream(tools: list[str]) -> FastMCP:
    mcp = FastMCP("upstream")
    for name in tools:

        def _tool(text: str, _n=name) -> str:
            return f"{_n}:{text}"

        _tool.__name__ = name
        _tool.__doc__ = f"ToolRow {name}."
        mcp.tool(_tool)
    return mcp


def _units(engine, redis) -> SqlAlchemyUnitOfWorkFactory:
    return SqlAlchemyUnitOfWorkFactory(session_factory(engine), redis)


def _discovery(engine, redis, probe, clock: Clock | None = None) -> DiscoveryService:
    """A discovery service whose failure streak lives in Valkey, as in production."""
    units = _units(engine, redis)
    health = UpstreamHealth(units, ValkeyFailureStreak(redis), RuntimeConfig(units))
    return DiscoveryService(units, probe, health=health, clock=clock or SystemClock())


def factory_for(upstream: FastMCP):
    def factory(server, extra_headers, *, observer=None):
        return Client(upstream, mode=connect_mode(server.protocol_mode))

    return factory


def failing_factory(server, extra_headers, *, observer=None):
    raise ConnectionError("upstream down")


async def seed_server(engine, name="srv", protocol_mode="auto") -> McpServerRow:
    factory = session_factory(engine)
    async with factory() as db:
        server = McpServerRow(name=name, url="http://upstream:1/mcp", protocol_mode=protocol_mode)
        db.add(server)
        await db.commit()
        await db.refresh(server)
        return server


async def test_discover_syncs_tools(engine, redis):
    server = await seed_server(engine)
    upstream = make_upstream(["alpha", "beta"])
    svc = _discovery(engine, redis, FastMcpUpstreamProbe(factory_for(upstream)))

    result = await svc.discover(server.id)
    assert result.error is None
    assert result.discovered == 2
    assert result.changed == 2

    async with session_factory(engine)() as db:
        names = {t.name for t in (await db.execute(select(ToolRow))).scalars()}
        assert names == {"alpha", "beta"}
        srv = (await db.execute(select(McpServerRow))).scalar_one()
        assert srv.health_status == HealthStatus.OK


class OverlappingProbe:
    """Probes for real, then holds the answer until a second probe has started (or a
    short window closes), so two unserialized discoveries both read the tool cache
    before either has written it."""

    def __init__(self, inner: FastMcpUpstreamProbe) -> None:
        self._inner = inner
        self._started = 0
        self._second = asyncio.Event()

    async def probe(self, server, headers) -> ProbeResult:
        self._started += 1
        if self._started >= 2:
            self._second.set()
        result = await self._inner.probe(server, headers)
        try:
            await asyncio.wait_for(self._second.wait(), 0.3)
        except TimeoutError:
            pass
        return result


async def test_ups39_concurrent_discoveries_store_each_tool_once(engine, redis):
    """UPS-39: two discoveries of one server at once both succeed and store each tool
    once, where unserialized they would both insert and the second would fail."""
    server = await seed_server(engine)
    upstream = make_upstream(["alpha", "beta"])
    svc = _discovery(engine, redis, OverlappingProbe(FastMcpUpstreamProbe(factory_for(upstream))))

    first, second = await asyncio.gather(svc.discover(server.id), svc.discover(server.id))

    assert first.error is None and second.error is None
    assert sorted([first.changed, second.changed]) == [0, 2]
    async with session_factory(engine)() as db:
        names = [t.name for t in (await db.execute(select(ToolRow))).scalars()]
    assert sorted(names) == ["alpha", "beta"]


class HeldProbe:
    """Probes for real, then holds the answer until released."""

    def __init__(self, inner: FastMcpUpstreamProbe) -> None:
        self._inner = inner
        self.probing = asyncio.Event()
        self.release = asyncio.Event()

    async def probe(self, server, headers) -> ProbeResult:
        self.probing.set()
        result = await self._inner.probe(server, headers)
        await self.release.wait()
        return result


def _servers(uow) -> ServerService:
    return ServerService(uow, discovery=NoopToolDiscovery(), public_base="http://gw")


async def _stored_servers(engine) -> list[McpServerRow]:
    async with session_factory(engine)() as db:
        return list((await db.execute(select(McpServerRow))).scalars())


async def _stored_tools(engine) -> list[ToolRow]:
    async with session_factory(engine)() as db:
        return list((await db.execute(select(ToolRow))).scalars())


async def test_ups40_a_delete_during_a_discovery_waits_and_the_server_stays_deleted(engine, redis):
    """UPS-40: a delete sent while a discovery of the server probes waits for it to commit,
    then removes the server with everything the discovery stored."""
    server = await seed_server(engine)
    probe = HeldProbe(FastMcpUpstreamProbe(factory_for(make_upstream(["alpha"]))))
    # one factory for both, as the gateway has: it holds the process-local locks sqlite uses
    units = _units(engine, redis)
    health = UpstreamHealth(units, ValkeyFailureStreak(redis), RuntimeConfig(units))
    svc = DiscoveryService(units, probe, health=health, clock=SystemClock())

    async def delete() -> None:
        async with units.open() as uow:
            await _servers(uow).delete("srv")

    discovering = asyncio.create_task(svc.discover(server.id))
    await probe.probing.wait()
    deleting = asyncio.create_task(delete())
    await asyncio.sleep(0.05)
    waited = not deleting.done()
    probe.release.set()
    result = await discovering
    await deleting

    assert waited
    assert result.error is None
    assert await _stored_servers(engine) == []
    assert await _stored_tools(engine) == []


async def test_ups40_a_server_removed_under_a_discovery_is_not_stored_again(engine, redis):
    """UPS-40: a server removed without the lock while its discovery probes stays removed;
    the discovery reports it not found and stores no tool for it."""
    server = await seed_server(engine)
    probe = HeldProbe(FastMcpUpstreamProbe(factory_for(make_upstream(["alpha"]))))
    svc = _discovery(engine, redis, probe)

    discovering = asyncio.create_task(svc.discover(server.id))
    await probe.probing.wait()
    async with session_factory(engine)() as db:
        await db.delete(await db.get(McpServerRow, server.id))
        await db.commit()
    probe.release.set()
    result = await discovering

    assert result.error == "server not found"
    assert await _stored_servers(engine) == []
    assert await _stored_tools(engine) == []


async def test_ups40_a_rename_during_a_discovery_is_kept(engine, redis):
    """UPS-40: a rename saved while a discovery probes is kept; the discovery stores only
    what it found out about the server."""
    server = await seed_server(engine)
    probe = HeldProbe(FastMcpUpstreamProbe(factory_for(make_upstream(["alpha"]))))
    svc = _discovery(engine, redis, probe)

    discovering = asyncio.create_task(svc.discover(server.id))
    await probe.probing.wait()
    async with _units(engine, redis).open() as uow:
        await _servers(uow).rename("srv", "renamed", force=False)
    probe.release.set()
    result = await discovering

    assert result.error is None
    [stored] = await _stored_servers(engine)
    assert stored.name == "renamed"
    assert stored.connection_state == ConnectionState.READY
    assert "tools" in stored.capabilities


async def test_discover_captures_capabilities(engine, redis):
    """UPS-22: the upstream's advertised capabilities are snapshotted for PROT-11."""
    server = await seed_server(engine)
    upstream = FastMCP("caps")

    @upstream.tool
    def t(x: str) -> str:
        return x

    @upstream.prompt
    def p() -> str:
        return "hi"

    @upstream.resource("res://a")
    def r() -> str:
        return "a"

    svc = _discovery(engine, redis, FastMcpUpstreamProbe(factory_for(upstream)))
    await svc.discover(server.id)

    async with session_factory(engine)() as db:
        srv = (await db.execute(select(McpServerRow))).scalar_one()
    assert "tools" in srv.capabilities
    assert "prompts" in srv.capabilities
    assert "resources" in srv.capabilities


async def test_discover_records_negotiated_protocol_version(engine, redis):
    """UPS-10/PROT-21: auto mode adopts the modern era; legacy mode keeps the handshake."""
    modern = await seed_server(engine, name="modern")
    legacy = await seed_server(engine, name="legacy", protocol_mode="legacy")
    svc = _discovery(engine, redis, FastMcpUpstreamProbe(factory_for(make_upstream(["alpha"]))))

    await svc.discover(modern.id)
    await svc.discover(legacy.id)

    async with session_factory(engine)() as db:
        versions = {
            s.name: s.protocol_version for s in (await db.execute(select(McpServerRow))).scalars()
        }
    assert versions == {"modern": "2026-07-28", "legacy": "2025-11-25"}


async def test_rediscovery_is_hash_stable(engine, redis):
    """UPS-18: unchanged definitions produce zero writes on re-sync."""
    server = await seed_server(engine)
    upstream = make_upstream(["alpha"])
    svc = _discovery(engine, redis, FastMcpUpstreamProbe(factory_for(upstream)))

    first = await svc.discover(server.id)
    second = await svc.discover(server.id)
    assert first.changed == 1
    assert second.changed == 0


async def test_vanished_tool_kept_stale(engine, redis):
    """UPS-19: a tool that disappears upstream stays cached, marked stale."""
    server = await seed_server(engine)
    svc = _discovery(
        engine, redis, FastMcpUpstreamProbe(factory_for(make_upstream(["alpha", "beta"])))
    )
    await svc.discover(server.id)

    svc2 = _discovery(engine, redis, FastMcpUpstreamProbe(factory_for(make_upstream(["alpha"]))))
    await svc2.discover(server.id)

    async with session_factory(engine)() as db:
        tools = {t.name: t for t in (await db.execute(select(ToolRow))).scalars()}
        assert set(tools) == {"alpha", "beta"}  # beta kept
        assert tools["alpha"].stale_since is None
        assert tools["beta"].stale_since is not None


async def test_ups19_stale_since_is_the_injected_instant(engine, redis):
    """UPS-19: a vanished tool's ``stale_since`` and the server's ``last_discovered_at`` are the
    instant the injected clock reads, not the wall clock's."""
    server = await seed_server(engine)
    first = datetime(2026, 10, 1, 9, tzinfo=UTC)
    clock = ManualClock(first)
    full = FastMcpUpstreamProbe(factory_for(make_upstream(["alpha", "beta"])))
    await _discovery(engine, redis, full, clock).discover(server.id)

    clock.advance(timedelta(hours=1))
    shrunk = FastMcpUpstreamProbe(factory_for(make_upstream(["alpha"])))
    await _discovery(engine, redis, shrunk, clock).discover(server.id)

    async with _units(engine, redis).open() as uow:
        stored = await uow.servers.get(server.id)
        tools = {t.name: t for t in await uow.tools.for_server(server.id)}
    assert stored is not None
    assert stored.last_discovered_at == first + timedelta(hours=1)
    assert tools["beta"].stale_since == first + timedelta(hours=1)
    assert tools["alpha"].stale_since is None


async def test_ups19_failed_probe_makes_nothing_stale(engine, redis):
    """UPS-19: a probe that fails leaves every cached tool as it was."""
    server = await seed_server(engine)
    ok = _discovery(engine, redis, FastMcpUpstreamProbe(factory_for(make_upstream(["alpha"]))))
    await ok.discover(server.id)

    down = _discovery(engine, redis, FastMcpUpstreamProbe(failing_factory))
    result = await down.discover(server.id, prune=True)

    assert result.error is not None
    async with session_factory(engine)() as db:
        [alpha] = (await db.execute(select(ToolRow))).scalars().all()
        assert alpha.stale_since is None


async def test_health_error_after_consecutive_failures_and_self_heal(engine, redis):
    """UPS-4: N consecutive failures -> error; success resets to ok."""
    server = await seed_server(engine)
    svc = _discovery(engine, redis, FastMcpUpstreamProbe(failing_factory))

    await svc.discover(server.id)
    await svc.discover(server.id)
    async with session_factory(engine)() as db:
        assert (await db.execute(select(McpServerRow))).scalar_one().health_status != (
            HealthStatus.ERROR
        )

    await svc.discover(server.id)  # the third consecutive failure (the default) trips it
    async with session_factory(engine)() as db:
        srv = (await db.execute(select(McpServerRow))).scalar_one()
        assert srv.health_status == HealthStatus.ERROR
        assert srv.last_error is not None

    svc._probe = FastMcpUpstreamProbe(factory_for(make_upstream(["alpha"])))  # upstream recovers
    result = await svc.discover(server.id)
    assert result.error is None
    async with session_factory(engine)() as db:
        srv = (await db.execute(select(McpServerRow))).scalar_one()
        assert srv.health_status == HealthStatus.OK
        assert srv.last_error is None


def factory_by_name(upstreams: dict[str, FastMCP]):
    """Route each server to its own upstream; a name without one is unreachable."""

    def factory(server, extra_headers, *, observer=None):
        upstream = upstreams.get(server.name)
        if upstream is None:
            raise ConnectionError(f"{server.name} unreachable")
        return Client(upstream, mode=connect_mode(server.protocol_mode))

    return factory


async def test_sweep_probes_every_server_past_a_failing_one(engine, redis):
    """UPS-23: one server's failure never stops the sweep for the rest."""
    await seed_server(engine, name="down")
    await seed_server(engine, name="up")
    svc = _discovery(
        engine,
        redis,
        FastMcpUpstreamProbe(factory_by_name({"up": make_upstream(["alpha", "beta"])})),
    )

    sweep = await svc.discover_all()

    assert (sweep.servers, sweep.failed, sweep.changed) == (2, 1, 2)
    async with session_factory(engine)() as db:
        assert {t.name for t in (await db.execute(select(ToolRow))).scalars()} == {
            "alpha",
            "beta",
        }


async def test_sweep_heals_a_server_unreachable_at_registration(engine, redis):
    """UPS-23: a server whose first discovery failed gets its tools on the next sweep."""
    server = await seed_server(engine)
    upstreams: dict[str, FastMCP] = {}
    svc = _discovery(engine, redis, FastMcpUpstreamProbe(factory_by_name(upstreams)))

    assert (await svc.discover(server.id)).error is not None  # e.g. its container is not up yet
    upstreams["srv"] = make_upstream(["alpha"])
    sweep = await svc.discover_all()

    assert (sweep.servers, sweep.failed, sweep.changed) == (1, 0, 1)
    async with session_factory(engine)() as db:
        srv = (await db.execute(select(McpServerRow))).scalar_one()
        assert srv.health_status == HealthStatus.OK
        assert [t.name for t in (await db.execute(select(ToolRow))).scalars()] == ["alpha"]


async def test_sweep_pages_through_every_server(engine, redis, monkeypatch):
    """UPS-23: servers beyond the first page are swept too."""
    from bundlemcp.application.discovery import discovery_service

    monkeypatch.setattr(discovery_service, "SWEEP_PAGE_SIZE", 2)
    for i in range(5):
        await seed_server(engine, name=f"srv{i}")
    svc = _discovery(engine, redis, FastMcpUpstreamProbe(factory_for(make_upstream(["alpha"]))))

    sweep = await svc.discover_all()

    assert (sweep.servers, sweep.failed) == (5, 0)


async def test_sweep_moves_past_a_hanging_upstream(engine, redis, monkeypatch):
    """UPS-23: a probe that never answers times out as a failure; the sweep continues."""
    import asyncio

    from bundlemcp.application.discovery import discovery_service

    monkeypatch.setattr(discovery_service, "PROBE_TIMEOUT_SECONDS", 0.05)
    await seed_server(engine, name="hang")
    await seed_server(engine, name="up")
    live = FastMcpUpstreamProbe(factory_by_name({"up": make_upstream(["alpha"])}))

    class HangingForOne:
        async def probe(self, server, headers):
            if server.name == "hang":
                await asyncio.sleep(3600)
            return await live.probe(server, headers)

    svc = _discovery(engine, redis, HangingForOne())

    sweep = await svc.discover_all()

    assert (sweep.servers, sweep.failed, sweep.changed) == (2, 1, 1)
