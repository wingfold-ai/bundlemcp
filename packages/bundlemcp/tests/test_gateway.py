"""Gateway MCP-serving tests: the full endpoint flow against in-process upstreams.

Covers EP-3 auth, SES-1/2/3/4 sessions, BND-2/3 prefix routing, TM-2/3
curation, PROF-3 chatgpt re-annotation, MID-2/3 metering, AUD-1/2 audit,
FWD-2/3 identity forwarding.
"""


import pytest
from bundlemcp.api.app import create_app
from bundlemcp.gateway.metering import MeterContext, MeterDecision
from bundlemcp.models import (
    ApiKey,
    ApiKeyKind,
    AuditRecord,
    Bundle,
    BundleServer,
    BundleTool,
    Endpoint,
    McpServer,
    Tool,
)
from bundlemcp.security import API_KEY_PREFIX, display_prefix, generate_token, hash_token
from bundlemcp.settings import Settings
from bundlemcp.store import session_factory
from fakeredis.aioredis import FakeRedis
from fastmcp import Client, FastMCP
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select

ENDPOINT_KEY = generate_token(API_KEY_PREFIX)

# --- in-process upstreams ---------------------------------------------------

echo_server = FastMCP("echo")


@echo_server.tool
def say(text: str) -> str:
    """Echo the text."""
    return f"echo:{text}"


@echo_server.tool
def fail(text: str) -> str:
    """Always fails."""
    raise ValueError("boom")


notes_server = FastMCP("notes")


@notes_server.tool
def write_note(text: str) -> str:
    """Write a note (a write tool)."""
    return "written"


UPSTREAMS = {"echo": echo_server, "notes": notes_server}


def upstream_factory(server, extra_headers):
    client = Client(UPSTREAMS[server.name])
    client._test_extra_headers = extra_headers  # inspected by the forwarding test
    return client


class RecordingHook:
    """MID-3 hook double: records contexts, can deny."""

    fail_open = False

    def __init__(self):
        self.pre_calls: list[MeterContext] = []
        self.post_calls: list[tuple[MeterContext, str, int]] = []
        self.deny_reason: str | None = None

    async def pre_call(self, ctx: MeterContext) -> MeterDecision:
        self.pre_calls.append(ctx)
        if self.deny_reason:
            return MeterDecision(allowed=False, reason=self.deny_reason)
        return MeterDecision(allowed=True)

    async def post_call(self, ctx: MeterContext, status: str, duration_ms: int) -> None:
        self.post_calls.append((ctx, status, duration_ms))


@pytest.fixture
async def gateway(engine: AsyncEngine, redis: FakeRedis):
    settings = Settings(_env_file=None, database_url="sqlite+aiosqlite://")
    app = create_app(settings, engine=engine, redis=redis, client_factory=upstream_factory)

    hook = RecordingHook()

    factory = session_factory(engine)
    async with factory() as db:
        db.add(
            ApiKey(
                name="k",
                key_hash=hash_token(ENDPOINT_KEY),
                key_prefix=display_prefix(ENDPOINT_KEY),
                kind=ApiKeyKind.ENDPOINT,
            )
        )
        echo = McpServer(name="echo", url="http://echo/mcp")
        notes = McpServer(
            name="notes", url="http://notes/mcp", forward_headers={"x-tenant": "x-tenant"}
        )
        bundle = Bundle(name="main", description="Test bundle")
        db.add_all([echo, notes, bundle])
        await db.commit()
        for obj in (echo, notes, bundle):
            await db.refresh(obj)
        db.add_all(
            [
                BundleServer(bundle_id=bundle.id, server_id=echo.id),
                BundleServer(bundle_id=bundle.id, server_id=notes.id),
                Endpoint(name="main", bundle_id=bundle.id, auth_modes=["api_key"]),
                Endpoint(
                    name="gpt", bundle_id=bundle.id, profile="chatgpt", auth_modes=["api_key"]
                ),
            ]
        )
        # tool cache rows (normally written by discovery)
        for srv, tool_names in ((echo, ["say", "fail"]), (notes, ["write_note"])):
            for tn in tool_names:
                db.add(Tool(server_id=srv.id, name=tn, schema_hash="h", input_schema={}))
        await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://gw",
        headers={"Authorization": f"Bearer {ENDPOINT_KEY}"},
    ) as http:
        async with app.router.lifespan_context(app):
            app.state.gateway.metering = hook
            yield http, app, hook


async def _initialize(http, endpoint="main") -> str:
    resp = await http.post(
        f"/{endpoint}/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25", "capabilities": {}},
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.headers["mcp-session-id"]


async def _rpc(http, endpoint, session_id, method, params=None, id_=2):
    return await http.post(
        f"/{endpoint}/mcp",
        headers={"Mcp-Session-Id": session_id},
        json={"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}},
    )


async def test_auth_required_and_challenge(gateway):
    """EP-3: 401 with WWW-Authenticate when unauthenticated."""
    http, app, hook = gateway
    resp = await http.post(
        "/main/mcp", json={"method": "initialize"}, headers={"Authorization": ""}
    )
    assert resp.status_code == 401
    assert "resource_metadata" in resp.headers["WWW-Authenticate"]


async def test_initialize_and_list_tools_prefixed(gateway):
    """SES-1, BND-2: prefixed names; bundle description as instructions."""
    http, app, hook = gateway
    session = await _initialize(http)

    resp = await _rpc(http, "main", session, "tools/list")
    tools = {t["name"] for t in resp.json()["result"]["tools"]}
    assert tools == {"echo__say", "echo__fail", "notes__write_note"}


async def test_call_routes_by_prefix(gateway):
    """BND-3 + MID-3: success path with metering pre/post."""
    http, app, hook = gateway
    session = await _initialize(http)

    resp = await _rpc(
        http, "main", session, "tools/call", {"name": "echo__say", "arguments": {"text": "hi"}}
    )
    result = resp.json()["result"]
    assert result["content"][0]["text"] == "echo:hi"
    assert not result.get("isError")

    assert len(hook.pre_calls) == 1
    ctx = hook.pre_calls[0]
    assert (ctx.bundle, ctx.server, ctx.tool) == ("main", "echo", "say")
    assert ctx.sub.startswith("api_key:")
    assert hook.post_calls[0][1] == "success"


async def test_upstream_iserror_maps_to_error_status(gateway):
    """MID-3: isError:true result -> post_call status=error (refund trigger)."""
    http, app, hook = gateway
    session = await _initialize(http)

    resp = await _rpc(
        http, "main", session, "tools/call", {"name": "echo__fail", "arguments": {"text": "x"}}
    )
    assert resp.json()["result"]["isError"] is True
    assert hook.post_calls[-1][1] == "error"


async def test_metering_deny_blocks_upstream(gateway):
    """MID-3: deny -> structured error, no upstream call, audit DENIED."""
    http, app, hook = gateway
    session = await _initialize(http)
    hook.deny_reason = "insufficient_credits"

    resp = await _rpc(
        http, "main", session, "tools/call", {"name": "echo__say", "arguments": {"text": "x"}}
    )
    assert resp.json()["error"]["message"] == "insufficient_credits"
    assert hook.post_calls == []  # pre denied -> no post


async def test_unknown_session_404(gateway):
    """SES-3."""
    http, app, hook = gateway
    resp = await _rpc(http, "main", "does-not-exist", "tools/list")
    assert resp.status_code == 404


async def test_session_survives_across_transports(gateway):
    """SES-2 proxy for any-replica: a second HTTP client reuses the session."""
    http, app, hook = gateway
    session = await _initialize(http)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://gw2",
        headers={"Authorization": f"Bearer {ENDPOINT_KEY}"},
    ) as other:
        resp = await _rpc(other, "main", session, "ping")
        assert resp.status_code == 200
        assert resp.json()["result"] == {}


async def test_delete_terminates_session(gateway):
    """SES-4."""
    http, app, hook = gateway
    session = await _initialize(http)
    resp = await http.request("DELETE", "/main/mcp", headers={"Mcp-Session-Id": session})
    assert resp.status_code == 204
    resp = await _rpc(http, "main", session, "tools/list")
    assert resp.status_code == 404


async def test_disabled_tool_hidden_and_blocked(gateway):
    """TM-2 in list AND call."""
    http, app, hook = gateway
    factory = app.state.session_factory
    async with factory() as db:
        bundle = (await db.execute(select(Bundle))).scalar_one()
        tool = (await db.execute(select(Tool).where(Tool.name == "say"))).scalar_one()
        db.add(BundleTool(bundle_id=bundle.id, tool_id=tool.id, enabled=False))
        await db.commit()

    session = await _initialize(http)
    listing = await _rpc(http, "main", session, "tools/list")
    assert "echo__say" not in {t["name"] for t in listing.json()["result"]["tools"]}

    call = await _rpc(
        http, "main", session, "tools/call", {"name": "echo__say", "arguments": {"text": "x"}}
    )
    assert "Unknown tool" in call.json()["error"]["message"]


async def test_override_rename_routes_back(gateway):
    """TM-3: override name is presented and maps back to the origin tool."""
    http, app, hook = gateway
    factory = app.state.session_factory
    async with factory() as db:
        bundle = (await db.execute(select(Bundle))).scalar_one()
        tool = (await db.execute(select(Tool).where(Tool.name == "say"))).scalar_one()
        db.add(BundleTool(bundle_id=bundle.id, tool_id=tool.id, override_name="speak"))
        await db.commit()

    session = await _initialize(http)
    listing = await _rpc(http, "main", session, "tools/list")
    names = {t["name"] for t in listing.json()["result"]["tools"]}
    assert "speak" in names and "echo__say" not in names

    call = await _rpc(
        http, "main", session, "tools/call", {"name": "speak", "arguments": {"text": "y"}}
    )
    assert call.json()["result"]["content"][0]["text"] == "echo:y"


async def test_chatgpt_profile_reannotates(gateway):
    """PROF-3: chatgpt endpoint presents every tool as read-safe."""
    http, app, hook = gateway
    session = await _initialize(http, endpoint="gpt")
    listing = await _rpc(http, "gpt", session, "tools/list")
    for tool in listing.json()["result"]["tools"]:
        assert tool["annotations"]["readOnlyHint"] is True
        assert tool["annotations"]["destructiveHint"] is False


async def test_default_profile_does_not_reannotate(gateway):
    http, app, hook = gateway
    session = await _initialize(http, endpoint="main")
    listing = await _rpc(http, "main", session, "tools/list")
    say = next(t for t in listing.json()["result"]["tools"] if t["name"] == "echo__say")
    assert "annotations" not in say or say["annotations"].get("readOnlyHint") is not True


async def test_audit_records_written(gateway):
    """AUD-1/AUD-2: success and denied calls produce audit records."""
    http, app, hook = gateway
    session = await _initialize(http)
    say_a = {"name": "echo__say", "arguments": {"text": "a"}}
    await _rpc(http, "main", session, "tools/call", say_a)
    hook.deny_reason = "insufficient_credits"
    say_b = {"name": "echo__say", "arguments": {"text": "b"}}
    await _rpc(http, "main", session, "tools/call", say_b)

    # audit is async (AUD-3) — drain the queue
    await app.state.gateway.audit._queue.join()
    async with app.state.session_factory() as db:
        records = (await db.execute(select(AuditRecord))).scalars().all()
    statuses = sorted(r.status for r in records)
    assert statuses == ["denied", "success"]
    denied = next(r for r in records if r.status == "denied")
    assert denied.denied_reason == "insufficient_credits"
    ok = next(r for r in records if r.status == "success")
    assert (ok.endpoint_name, ok.server_name, ok.tool_name) == ("main", "echo", "say")
    assert ok.duration_ms is not None


async def test_identity_header_injected_and_spoof_stripped(gateway):
    """FWD-2/FWD-3: X-MCP-User injected from resolved identity; client value ignored."""
    http, app, hook = gateway
    captured: dict = {}
    original = app.state.gateway.client_factory

    def capturing_factory(server, extra_headers):
        captured.update(extra_headers)
        return original(server, extra_headers)

    app.state.gateway.client_factory = capturing_factory
    session = await _initialize(http)
    await http.post(
        "/main/mcp",
        headers={
            "Mcp-Session-Id": session,
            "X-MCP-User": "spoofed",
            "x-tenant": "tenant-42",
        },
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "notes__write_note", "arguments": {"text": "n"}},
        },
    )
    assert captured["X-MCP-User"].startswith("api_key:")  # injected, not "spoofed"
    assert captured["x-tenant"] == "tenant-42"  # FWD-1 mapping
