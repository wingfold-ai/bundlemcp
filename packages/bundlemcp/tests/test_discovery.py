"""Discovery tests (spec 11 DISC-1/2/3, spec 10 SRV-4) against in-process FastMCP servers."""

from bundlemcp.gateway.discovery import DiscoveryService
from bundlemcp.models import HealthStatus, McpServer, Tool
from bundlemcp.store import session_factory
from fastmcp import Client, FastMCP
from sqlmodel import select


def make_upstream(tools: list[str]) -> FastMCP:
    mcp = FastMCP("upstream")
    for name in tools:
        def _tool(text: str, _n=name) -> str:
            return f"{_n}:{text}"
        _tool.__name__ = name
        _tool.__doc__ = f"Tool {name}."
        mcp.tool(_tool)
    return mcp


def factory_for(upstream: FastMCP):
    def factory(server, extra_headers):
        return Client(upstream)

    return factory


def failing_factory(server, extra_headers):
    raise ConnectionError("upstream down")


async def seed_server(engine, name="srv") -> McpServer:
    factory = session_factory(engine)
    async with factory() as db:
        server = McpServer(name=name, url="http://upstream:1/mcp")
        db.add(server)
        await db.commit()
        await db.refresh(server)
        return server


async def test_discover_syncs_tools(engine):
    server = await seed_server(engine)
    upstream = make_upstream(["alpha", "beta"])
    svc = DiscoveryService(session_factory(engine), factory_for(upstream))

    result = await svc.discover(server.id)
    assert result.error is None
    assert result.discovered == 2
    assert result.changed == 2

    async with session_factory(engine)() as db:
        names = {t.name for t in (await db.execute(select(Tool))).scalars()}
        assert names == {"alpha", "beta"}
        srv = (await db.execute(select(McpServer))).scalar_one()
        assert srv.health_status == HealthStatus.OK


async def test_discover_captures_capabilities(engine):
    """DISC-6: the upstream's advertised capabilities are snapshotted for PROT-11."""
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

    svc = DiscoveryService(session_factory(engine), factory_for(upstream))
    await svc.discover(server.id)

    async with session_factory(engine)() as db:
        srv = (await db.execute(select(McpServer))).scalar_one()
    assert "tools" in srv.capabilities
    assert "prompts" in srv.capabilities
    assert "resources" in srv.capabilities


async def test_rediscovery_is_hash_stable(engine):
    """DISC-2: unchanged definitions produce zero writes on re-sync."""
    server = await seed_server(engine)
    upstream = make_upstream(["alpha"])
    svc = DiscoveryService(session_factory(engine), factory_for(upstream))

    first = await svc.discover(server.id)
    second = await svc.discover(server.id)
    assert first.changed == 1
    assert second.changed == 0


async def test_vanished_tool_kept_stale(engine):
    """DISC-3: tools that disappear upstream stay cached with old last_seen_at."""
    server = await seed_server(engine)
    svc = DiscoveryService(session_factory(engine), factory_for(make_upstream(["alpha", "beta"])))
    await svc.discover(server.id)

    svc2 = DiscoveryService(session_factory(engine), factory_for(make_upstream(["alpha"])))
    await svc2.discover(server.id)

    async with session_factory(engine)() as db:
        tools = {t.name: t for t in (await db.execute(select(Tool))).scalars()}
        assert set(tools) == {"alpha", "beta"}  # beta kept
        assert tools["alpha"].last_seen_at > tools["beta"].last_seen_at


async def test_health_error_after_consecutive_failures_and_self_heal(engine):
    """SRV-4: N consecutive failures -> error; success resets to ok."""
    server = await seed_server(engine)
    svc = DiscoveryService(session_factory(engine), failing_factory, max_attempts=2)

    await svc.discover(server.id)
    async with session_factory(engine)() as db:
        assert (await db.execute(select(McpServer))).scalar_one().health_status != (
            HealthStatus.ERROR
        )

    await svc.discover(server.id)  # second consecutive failure trips it
    async with session_factory(engine)() as db:
        srv = (await db.execute(select(McpServer))).scalar_one()
        assert srv.health_status == HealthStatus.ERROR
        assert srv.last_error is not None

    svc._client_factory = factory_for(make_upstream(["alpha"]))  # upstream recovers
    result = await svc.discover(server.id)
    assert result.error is None
    async with session_factory(engine)() as db:
        srv = (await db.execute(select(McpServer))).scalar_one()
        assert srv.health_status == HealthStatus.OK
        assert srv.last_error is None
