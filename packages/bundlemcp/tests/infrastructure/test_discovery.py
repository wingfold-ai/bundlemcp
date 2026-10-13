"""Discovery tests (UPS-17/18/19, UPS-4) against in-process FastMCP servers."""

from bundlemcp.application.discovery.discovery_service import DiscoveryService
from bundlemcp.domain.servers.health_status import HealthStatus
from bundlemcp.infrastructure.fastmcp.upstream_probe import FastMcpUpstreamProbe
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.postgres.rows.tool_row import ToolRow
from bundlemcp.infrastructure.postgres.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWorkFactory
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


def factory_for(upstream: FastMCP):
    def factory(server, extra_headers, *, observer=None):
        return Client(upstream, mode=server.protocol_mode)

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
    svc = DiscoveryService(_units(engine, redis), FastMcpUpstreamProbe(factory_for(upstream)))

    result = await svc.discover(server.id)
    assert result.error is None
    assert result.discovered == 2
    assert result.changed == 2

    async with session_factory(engine)() as db:
        names = {t.name for t in (await db.execute(select(ToolRow))).scalars()}
        assert names == {"alpha", "beta"}
        srv = (await db.execute(select(McpServerRow))).scalar_one()
        assert srv.health_status == HealthStatus.OK


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

    svc = DiscoveryService(_units(engine, redis), FastMcpUpstreamProbe(factory_for(upstream)))
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
    svc = DiscoveryService(
        _units(engine, redis), FastMcpUpstreamProbe(factory_for(make_upstream(["alpha"])))
    )

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
    svc = DiscoveryService(_units(engine, redis), FastMcpUpstreamProbe(factory_for(upstream)))

    first = await svc.discover(server.id)
    second = await svc.discover(server.id)
    assert first.changed == 1
    assert second.changed == 0


async def test_vanished_tool_kept_stale(engine, redis):
    """UPS-19: tools that disappear upstream stay cached with old last_seen_at."""
    server = await seed_server(engine)
    svc = DiscoveryService(
        _units(engine, redis), FastMcpUpstreamProbe(factory_for(make_upstream(["alpha", "beta"])))
    )
    await svc.discover(server.id)

    svc2 = DiscoveryService(
        _units(engine, redis), FastMcpUpstreamProbe(factory_for(make_upstream(["alpha"])))
    )
    await svc2.discover(server.id)

    async with session_factory(engine)() as db:
        tools = {t.name: t for t in (await db.execute(select(ToolRow))).scalars()}
        assert set(tools) == {"alpha", "beta"}  # beta kept
        assert tools["alpha"].last_seen_at > tools["beta"].last_seen_at


async def test_health_error_after_consecutive_failures_and_self_heal(engine, redis):
    """UPS-4: N consecutive failures -> error; success resets to ok."""
    server = await seed_server(engine)
    svc = DiscoveryService(
        _units(engine, redis), FastMcpUpstreamProbe(failing_factory), max_attempts=2
    )

    await svc.discover(server.id)
    async with session_factory(engine)() as db:
        assert (await db.execute(select(McpServerRow))).scalar_one().health_status != (
            HealthStatus.ERROR
        )

    await svc.discover(server.id)  # second consecutive failure trips it
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
        return Client(upstream, mode=server.protocol_mode)

    return factory


async def test_sweep_probes_every_server_past_a_failing_one(engine, redis):
    """UPS-23: one server's failure never stops the sweep for the rest."""
    await seed_server(engine, name="down")
    await seed_server(engine, name="up")
    svc = DiscoveryService(
        _units(engine, redis),
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
    svc = DiscoveryService(_units(engine, redis), FastMcpUpstreamProbe(factory_by_name(upstreams)))

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
    svc = DiscoveryService(
        _units(engine, redis), FastMcpUpstreamProbe(factory_for(make_upstream(["alpha"])))
    )

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

    svc = DiscoveryService(_units(engine, redis), HangingForOne())

    sweep = await svc.discover_all()

    assert (sweep.servers, sweep.failed, sweep.changed) == (2, 1, 1)
