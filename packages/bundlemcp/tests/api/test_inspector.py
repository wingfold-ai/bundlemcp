"""The admin UI's MCP inspector through the management API, on in-process upstreams."""

import json
from contextlib import asynccontextmanager

import pytest
import structlog
from bundlemcp.domain.servers.identity_mode import IdentityMode
from bundlemcp.domain.servers.server_auth_mode import ServerAuthMode
from bundlemcp.infrastructure.fastmcp.connect_mode import connect_mode
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.audit_record_row import AuditRecordRow
from bundlemcp.infrastructure.postgres.rows.bundle_row import BundleRow
from bundlemcp.infrastructure.postgres.rows.bundle_server_row import BundleServerRow
from bundlemcp.infrastructure.postgres.rows.bundle_tool_row import BundleToolRow
from bundlemcp.infrastructure.postgres.rows.endpoint_row import EndpointRow
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.postgres.rows.tool_row import ToolRow
from fastmcp import Client, Context, FastMCP
from httpx import AsyncClient
from sqlmodel import select

from tests.conftest import ENDPOINT_KEY, SERVICE_KEY, seed_api_key, serving

SECRET = "weather-secret-7f3a91"

weather = FastMCP("weather", version="1.2.0")


@weather.tool
def forecast(city: str) -> str:
    """Tomorrow's weather for a city."""
    return f"sunny in {city}"


@weather.tool
def leak() -> str:
    """Repeats the credential it was called with, as a careless upstream might."""
    return f"you sent {SECRET}"


@weather.tool
async def slow(ctx: Context) -> str:
    """Reports progress twice before answering."""
    await ctx.report_progress(progress=1, total=2, message="half")
    await ctx.report_progress(progress=2, total=2, message="done")
    return "finished"


@weather.tool
def broken() -> str:
    """Always fails."""
    raise ValueError("no forecast today")


class RecordingFactory:
    """The client factory double: records what each connection would send."""

    def __init__(self) -> None:
        self.connections: list[tuple[str, dict[str, str]]] = []

    def __call__(self, server, extra_headers, *, observer=None, **handlers):
        self.connections.append((server.name, {**server.static_headers, **extra_headers}))
        return Client(weather, mode=connect_mode(server.protocol_mode))


async def _seed(engine) -> None:
    async with session_factory(engine)() as db:
        server = McpServerRow(
            name="weather",
            url="http://weather/mcp",
            auth_mode=ServerAuthMode.STATIC_HEADERS,
            static_headers={"Authorization": f"Bearer {SECRET}"},
            protocol_mode="legacy",  # the handshake era here; the endpoint serves the other
        )
        personal = McpServerRow(
            name="mine",
            url="http://mine/mcp",
            auth_mode=ServerAuthMode.UPSTREAM_OAUTH,
            identity_mode=IdentityMode.PER_USER,
        )
        bundle = BundleRow(name="b1")
        db.add_all([server, personal, bundle])
        await db.commit()
        for row in (server, bundle):
            await db.refresh(row)
        tools = {
            name: ToolRow(
                server_id=server.id, name=name, schema_hash="h", input_schema={"type": "object"}
            )
            for name in ("forecast", "leak", "slow", "broken")
        }
        db.add_all(
            [
                *tools.values(),
                BundleServerRow(bundle_id=bundle.id, server_id=server.id),
                EndpointRow(
                    name="b1-chatgpt",
                    bundle_id=bundle.id,
                    profile="write_as_read",
                    auth_modes=["api_key"],
                ),
            ]
        )
        await db.commit()
        await db.refresh(tools["leak"])
        db.add(BundleToolRow(bundle_id=bundle.id, tool_id=tools["leak"].id, enabled=False))
        await db.commit()


@asynccontextmanager
async def _inspector(engine, redis, **overrides):
    await _seed(engine)
    await seed_api_key(engine, SERVICE_KEY)
    await seed_api_key(engine, ENDPOINT_KEY, name="endpoint", kind="endpoint")
    factory = RecordingFactory()
    async with serving(
        engine, redis, bearer=SERVICE_KEY, **{"client_factory": factory, **overrides}
    ) as (http, app):
        yield http, app, factory


UPSTREAM = {"kind": "upstream", "name": "weather"}
ENDPOINT = {"kind": "endpoint", "name": "b1-chatgpt", "credential": ENDPOINT_KEY}


def _events(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


async def _call(http: AsyncClient, target: dict, tool: str, arguments: dict | None = None):
    resp = await http.post(
        "/api/v1/inspector:call-tool",
        json={"target": target, "tool": tool, "arguments": arguments or {}},
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/event-stream")
    return _events(resp.text)


async def test_ui8_upstream_uses_stored_headers_never_returned(engine, redis):
    """UI-8: the stored header reaches the upstream; no response carries its value."""
    async with _inspector(engine, redis) as (http, _app, factory):
        connected = await http.post("/api/v1/inspector:connect", json={"target": UPSTREAM})
        listed = await http.post("/api/v1/inspector:list-tools", json={"target": UPSTREAM})
        events = await _call(http, UPSTREAM, "leak")

    assert connected.status_code == 200, connected.text
    assert connected.json()["server_info"]["name"] == "weather"
    assert "tools" in connected.json()["capabilities"]
    assert {t["name"] for t in listed.json()["tools"]} == {"forecast", "leak", "slow", "broken"}
    assert factory.connections[0] == ("weather", {"Authorization": f"Bearer {SECRET}"})
    for resp_text in (connected.text, listed.text, json.dumps(events)):
        assert SECRET not in resp_text
    assert "[redacted]" in events[-1][1]["result"]["content"][0]["text"]


async def test_ui8_endpoint_lists_what_its_clients_see(engine, redis):
    """UI-8: an endpoint target shows the curated, profile-annotated listing of its clients."""
    async with _inspector(engine, redis) as (http, _app, _factory):
        resp = await http.post("/api/v1/inspector:list-tools", json={"target": ENDPOINT})

    assert resp.status_code == 200, resp.text
    tools = {t["name"]: t for t in resp.json()["tools"]}
    assert set(tools) == {"weather__forecast", "weather__slow", "weather__broken"}
    for tool in tools.values():
        assert tool["annotations"]["readOnlyHint"] is True


async def test_ui8_endpoint_without_credential_is_refused(engine, redis):
    """UI-8: the endpoint's own authentication applies to the inspector."""
    async with _inspector(engine, redis) as (http, _app, _factory):
        resp = await http.post(
            "/api/v1/inspector:connect", json={"target": {"kind": "endpoint", "name": "b1-chatgpt"}}
        )

    assert resp.status_code == 502
    assert resp.json()["detail"].split(":")[0] in {"credential_required", "oauth_required"}


async def test_ui8_adhoc_target_connects_with_entered_headers(engine, redis):
    """UI-8: an ad-hoc URL is reached with the entered header, and nothing is stored."""
    target = {"kind": "adhoc", "url": "http://adhoc.example/mcp", "headers": {"X-Key": "abc123"}}
    async with _inspector(engine, redis) as (http, _app, factory):
        resp = await http.post("/api/v1/inspector:connect", json={"target": target})
        servers = await http.get("/api/v1/upstreams")

    assert resp.status_code == 200, resp.text
    assert resp.json()["server_info"]["version"] == "1.2.0"
    assert factory.connections == [("inspector", {"X-Key": "abc123"})]
    assert {s["name"] for s in servers.json()["items"]} == {"weather", "mine"}


async def test_ui8_target_kind_is_validated(engine, redis):
    """UI-8: a target kind other than upstream, endpoint or adhoc is rejected."""
    async with _inspector(engine, redis) as (http, _app, factory):
        resp = await http.post(
            "/api/v1/inspector:connect", json={"target": {"kind": "shell", "name": "x"}}
        )

    assert resp.status_code == 422
    assert factory.connections == []


async def test_ui9_ping_is_timed(engine, redis):
    """UI-9: a ping reports how long connecting and the ping itself took."""
    async with _inspector(engine, redis) as (http, _app, _factory):
        resp = await http.post("/api/v1/inspector:ping", json={"target": UPSTREAM})

    assert resp.status_code == 200, resp.text
    assert resp.json()["initialize_ms"] >= 0 and resp.json()["duration_ms"] >= 0


async def test_ui10_service_key_cannot_inspect_per_user_upstream(engine, redis):
    """UI-10: a per-user upstream needs a person's account, which a service key has not."""
    async with _inspector(engine, redis) as (http, _app, factory):
        resp = await http.post(
            "/api/v1/inspector:connect", json={"target": {"kind": "upstream", "name": "mine"}}
        )

    assert resp.status_code == 409
    assert "service key" in resp.json()["detail"]
    assert factory.connections == []


async def test_ui10_sec1_blocked_adhoc_url_is_refused(engine, redis):
    """UI-10, SEC-1: an ad-hoc URL in a blocked range is refused and nothing is sent."""
    await seed_api_key(engine, SERVICE_KEY)
    target = {"kind": "adhoc", "url": "http://169.254.169.254/mcp"}
    async with serving(engine, redis, bearer=SERVICE_KEY) as (http, _app):
        connected = await http.post("/api/v1/inspector:connect", json={"target": target})
        events = await _call(http, target, "anything")

    assert connected.status_code == 502
    assert connected.json()["detail"].startswith("egress_denied")
    assert events == [
        (
            "failure",
            {
                "type": "failure",
                "connection_state": "egress_denied",
                "detail": "The gateway's egress policy does not allow this address.",
            },
        )
    ]


async def test_ui10_inspector_requires_management_credentials(engine, redis):
    """UI-10: without an admin session or service key nothing is contacted."""
    async with _inspector(engine, redis) as (http, _app, factory):
        for route in ("connect", "ping", "list-tools"):
            resp = await http.post(
                f"/api/v1/inspector:{route}",
                json={"target": UPSTREAM},
                headers={"Authorization": ""},
            )
            assert resp.status_code == 401
        call = await http.post(
            "/api/v1/inspector:call-tool",
            json={"target": UPSTREAM, "tool": "forecast"},
            headers={"Authorization": f"Bearer {ENDPOINT_KEY}"},
        )

    assert call.status_code == 403
    assert factory.connections == []


async def test_ui9_progress_streams_before_the_result(engine, redis):
    """UI-9: progress notifications come first, then the result with its timings."""
    async with _inspector(engine, redis) as (http, _app, _factory):
        events = await _call(http, UPSTREAM, "slow")

    assert [name for name, _ in events] == ["progress", "progress", "result"]
    assert [data["message"] for _, data in events[:2]] == ["half", "done"]
    outcome = events[-1][1]
    assert outcome["is_error"] is False
    assert outcome["result"]["content"][0]["text"] == "finished"
    assert outcome["initialize_ms"] >= 0 and outcome["duration_ms"] >= 0


async def test_ui9_error_result_is_reported_as_error(engine, redis):
    """UI-9: a result with isError is shown as an error, with its content."""
    async with _inspector(engine, redis) as (http, _app, _factory):
        events = await _call(http, UPSTREAM, "broken")

    outcome = events[-1][1]
    assert outcome["is_error"] is True
    assert "no forecast today" in outcome["result"]["content"][0]["text"]


async def test_ui9_arguments_reach_the_tool(engine, redis):
    """UI-9: a call carries the arguments the form built."""
    async with _inspector(engine, redis) as (http, _app, _factory):
        events = await _call(http, ENDPOINT, "weather__forecast", {"city": "Bern"})

    assert events[-1][1]["result"]["content"][0]["text"] == "sunny in Bern"


async def test_ui11_endpoint_call_is_audited(engine, redis):
    """UI-11: a call through an endpoint writes one audit record, as any client's does."""
    async with _inspector(engine, redis) as (http, app, _factory):
        await _call(http, ENDPOINT, "weather__forecast", {"city": "Bern"})
        await app.state.container.audit.drain()
        async with app.state.container.session_factory() as db:
            records = (await db.execute(select(AuditRecordRow))).scalars().all()

    tool_calls = [r for r in records if r.tool_name == "forecast"]
    assert [(r.endpoint_name, r.status) for r in tool_calls] == [("b1-chatgpt", "success")]


async def test_ui11_upstream_call_is_logged_not_audited(engine, redis):
    """UI-11: a direct upstream call logs source=inspector and writes no audit record."""
    async with _inspector(engine, redis) as (http, app, _factory):
        with structlog.testing.capture_logs(
            processors=[structlog.contextvars.merge_contextvars]
        ) as logs:
            await _call(http, UPSTREAM, "forecast", {"city": "Bern"})
        await app.state.container.audit.drain()
        async with app.state.container.session_factory() as db:
            records = (await db.execute(select(AuditRecordRow))).scalars().all()

    called = [entry for entry in logs if entry["event"] == "inspector.tool_called"]
    assert called and all(entry["source"] == "inspector" for entry in called)
    assert called[0]["server"] == "weather"
    assert [r for r in records if r.tool_name == "forecast"] == []


@pytest.mark.parametrize("route", ["connect", "list-tools"])
async def test_ui8_unknown_upstream_is_not_found(engine, redis, route):
    async with _inspector(engine, redis) as (http, _app, _factory):
        resp = await http.post(
            f"/api/v1/inspector:{route}", json={"target": {"kind": "upstream", "name": "nope"}}
        )

    assert resp.status_code == 404
