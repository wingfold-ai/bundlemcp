"""Live tools/call requests count toward the upstream's health (UPS-4)."""

from bundlemcp.domain.servers.health_status import HealthStatus
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from sqlmodel import select

from tests.api.test_gateway import _initialize, _rpc, _running, upstream_factory

SAY = {"name": "echo__say", "arguments": {"text": "x"}}
FAIL = {"name": "echo__fail", "arguments": {"text": "x"}}


class _Unreachable:
    async def __aenter__(self):
        raise RuntimeError("Client failed to connect: All connection attempts failed")

    async def __aexit__(self, *exc):
        return False


class SwitchableUpstreams:
    """The echo upstream, until the test takes it down."""

    def __init__(self) -> None:
        self.down = False

    def __call__(self, server, extra_headers, *, observer=None, **handlers):
        if not self.down:
            return upstream_factory(server, extra_headers, observer=observer, **handlers)
        if observer is not None:  # what the HTTP transport notes for a refused connection
            observer.record_transport_failure()
        return _Unreachable()


async def _echo(engine) -> McpServerRow:
    async with session_factory(engine)() as db:
        rows = (await db.execute(select(McpServerRow))).scalars().all()
        return next(row for row in rows if row.name == "echo")


async def test_ups4_live_call_failures_count(engine, redis):
    """UPS-4: three calls that cannot reach the upstream mark it as failing."""
    upstreams = SwitchableUpstreams()
    async with _running(engine, redis, client_factory=upstreams) as (http, _app):
        session = await _initialize(http)
        upstreams.down = True
        for attempt in range(3):
            resp = await _rpc(http, "main", session, "tools/call", SAY, id_=10 + attempt)
            assert "error" in resp.json() or resp.json()["result"].get("isError")
            if attempt < 2:
                assert (await _echo(engine)).health_status != HealthStatus.ERROR
        echo = await _echo(engine)
        assert echo.health_status == HealthStatus.ERROR
        assert echo.last_error


async def test_ups4_tool_error_is_not_a_connection_failure(engine, redis):
    """UPS-4: a tool result with isError resets the streak and heals the server."""
    upstreams = SwitchableUpstreams()
    async with _running(engine, redis, client_factory=upstreams) as (http, _app):
        session = await _initialize(http)
        upstreams.down = True
        for attempt in range(3):
            await _rpc(http, "main", session, "tools/call", SAY, id_=20 + attempt)
        assert (await _echo(engine)).health_status == HealthStatus.ERROR
        upstreams.down = False
        resp = await _rpc(http, "main", session, "tools/call", FAIL, id_=30)
        assert resp.json()["result"]["isError"] is True
        echo = await _echo(engine)
        assert echo.health_status == HealthStatus.OK and echo.last_error is None
