"""Protocol-relay tests (spec 32): GET stream, list_changed, progress, cancel, elicitation.

SSE streaming can't go through httpx's ASGITransport (it buffers the whole
response), so these tests run the gateway on a real loopback uvicorn server —
still hermetic (no Docker, no external network; the upstreams are in-process
FastMCP via the injected client factory).

Two upstreams cover both protocol eras (PROT-21): ``relay`` is reached with the
handshake (``mode="legacy"``) and asks for client input with server-initiated
requests; ``modern`` is reached at 2026-07-28 and asks with an
``InputRequiredResult``. A handshake-era client sees both the same way (PROT-4).
"""

import asyncio
import contextlib
import json
import socket

import pytest
import uvicorn
from bundlemcp.domain.access.api_key_kind import ApiKeyKind
from bundlemcp.domain.shared.secrets import (
    API_KEY_PREFIX,
    display_prefix,
    generate_token,
    hash_token,
)
from bundlemcp.infrastructure.config.settings import EnvSettings
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.api_key_row import ApiKeyRow
from bundlemcp.infrastructure.postgres.rows.audit_record_row import AuditRecordRow
from bundlemcp.infrastructure.postgres.rows.bundle_row import BundleRow
from bundlemcp.infrastructure.postgres.rows.bundle_server_row import BundleServerRow
from bundlemcp.infrastructure.postgres.rows.endpoint_row import EndpointRow
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.postgres.rows.tool_row import ToolRow
from bundlemcp.main.app import create_app
from bundlemcp.main.composition_overrides import CompositionOverrides
from fakeredis.aioredis import FakeRedis
from fastmcp import Client, Context, FastMCP
from httpx import AsyncClient
from mcp.shared.inbound import NAME_BEARING_METHODS
from mcp.shared.subscriptions import SUBSCRIPTION_ID_META_KEY
from mcp.types import (
    CLIENT_CAPABILITIES_META_KEY,
    LOG_LEVEL_META_KEY,
    PROTOCOL_VERSION_META_KEY,
    ElicitRequest,
    ElicitRequestFormParams,
    InputRequiredResult,
)
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select

SERVICE_KEY = generate_token(API_KEY_PREFIX)
ENDPOINT_KEY = generate_token(API_KEY_PREFIX)

# --- in-process upstream with slow/progress tools ----------------------------

relay_server = FastMCP("relay")


@relay_server.tool
async def quick(text: str) -> str:
    """Fast tool."""
    return f"ok:{text}"


@relay_server.tool
async def slow_with_progress(steps: int, ctx: Context) -> str:
    """Reports progress each step (Context injected by FastMCP)."""
    for i in range(steps):
        await ctx.report_progress(progress=i + 1, total=steps)
        await asyncio.sleep(0.05)
    return "done"


@relay_server.tool
async def hang(seconds: float) -> str:
    """Sleeps without progress (timeout/cancel target)."""
    await asyncio.sleep(seconds)
    return "finished"


@relay_server.tool
async def ask_name(ctx: Context) -> str:
    """Elicits a name from the client (server->client request, PROT-4)."""
    result = await ctx.elicit("What is your name?", response_type=str)
    if result.action == "accept":
        return f"hello {result.data}"
    return "declined"


@relay_server.tool
async def read_roots(ctx: Context) -> str:
    """Requests the client's roots (server->client roots/list, PROT-4)."""
    result = await ctx.session.list_roots()
    return f"roots:{len(result.roots)}"


@relay_server.tool
async def emit_log(ctx: Context) -> str:
    """Emits an upstream log notification (PROT-7)."""
    await ctx.info("hello-log")
    return "logged"


# --- in-process modern upstream (2026-07-28): asks with input_required -------

modern_server = FastMCP("modern")


@modern_server.tool(name="ask_name")
async def modern_ask_name(ctx: Context) -> InputRequiredResult | str:
    """Asks for a name with the MRTR guard pattern (PROT-18 upstream side)."""
    answer = (ctx.input_responses or {}).get("name")
    if answer is not None and answer.action == "accept":
        return f"hello {answer.content['value']}"
    return InputRequiredResult(
        input_requests={
            "name": ElicitRequest(
                params=ElicitRequestFormParams(
                    message="What is your name?",
                    requested_schema={
                        "type": "object",
                        "properties": {"value": {"type": "string"}},
                    },
                )
            )
        },
        request_state="ask-name",
    )


UPSTREAMS = {"relay": relay_server, "modern": modern_server}


def upstream_factory(server, extra_headers, **handlers):
    # `relay` is pinned to the handshake era by its protocol_mode (SRV-10);
    # `modern` negotiates 2026-07-28 through server/discover.
    return Client(UPSTREAMS[server.name], mode=server.protocol_mode, **handlers)


async def seed(engine: AsyncEngine) -> None:
    factory = session_factory(engine)
    async with factory() as db:
        db.add_all(
            [
                ApiKeyRow(
                    name="svc",
                    key_hash=hash_token(SERVICE_KEY),
                    key_prefix=display_prefix(SERVICE_KEY),
                    kind=ApiKeyKind.SERVICE,
                ),
                ApiKeyRow(
                    name="ep",
                    key_hash=hash_token(ENDPOINT_KEY),
                    key_prefix=display_prefix(ENDPOINT_KEY),
                    kind=ApiKeyKind.ENDPOINT,
                ),
            ]
        )
        srv = McpServerRow(name="relay", url="http://relay/mcp", protocol_mode="legacy")
        modern = McpServerRow(name="modern", url="http://modern/mcp")
        bundle = BundleRow(name="main")
        db.add_all([srv, modern, bundle])
        await db.commit()
        await db.refresh(srv)
        await db.refresh(modern)
        await db.refresh(bundle)
        db.add(BundleServerRow(bundle_id=bundle.id, server_id=srv.id))
        db.add(BundleServerRow(bundle_id=bundle.id, server_id=modern.id))
        db.add(EndpointRow(name="main", bundle_id=bundle.id, auth_modes=["api_key"]))
        for tool in ("quick", "slow_with_progress", "hang", "ask_name", "read_roots", "emit_log"):
            db.add(ToolRow(server_id=srv.id, name=tool, schema_hash="h", input_schema={}))
        db.add(ToolRow(server_id=modern.id, name="ask_name", schema_hash="h", input_schema={}))
        await db.commit()


def make_app(engine, redis):
    settings = EnvSettings(_env_file=None, database_url="sqlite+aiosqlite://")
    return create_app(
        settings,
        overrides=CompositionOverrides(engine=engine, redis=redis, client_factory=upstream_factory),
    )


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.asynccontextmanager
async def running_app(app):
    """Serve `app` on a loopback uvicorn (real SSE streaming); yields base URL."""
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    try:
        for _ in range(200):
            if server.started:
                break
            await asyncio.sleep(0.02)
        assert server.started, "uvicorn did not start"
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(task, timeout=5)


@pytest.fixture
async def relay_env(engine: AsyncEngine, redis: FakeRedis):
    await seed(engine)
    app = make_app(engine, redis)
    async with running_app(app) as base_url:
        async with AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {ENDPOINT_KEY}"},
            timeout=10,
        ) as http:
            yield http, app, base_url


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


async def _read_stream_until(http, session_id, predicate, timeout=5, endpoint="main"):
    """Open the GET stream and return the first event matching predicate."""

    async def reader():
        async with http.stream(
            "GET", f"/{endpoint}/mcp", headers={"Mcp-Session-Id": session_id}
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    event = json.loads(line[6:])
                    if predicate(event):
                        return event
        return None

    return await asyncio.wait_for(reader(), timeout=timeout)


async def test_initialize_advertises_list_changed(relay_env):
    """PROT-11: tools.listChanged now true."""
    http, app, base_url = relay_env
    resp = await http.post(
        "/main/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert resp.json()["result"]["capabilities"]["tools"]["listChanged"] is True


async def test_get_stream_requires_session(relay_env):
    http, app, base_url = relay_env
    resp = await http.get("/main/mcp", headers={"Mcp-Session-Id": "ghost"})
    assert resp.status_code == 404


async def test_list_changed_reaches_stream_after_curation_change(relay_env):
    """EP-1a + BND-7: a management-API change fans out to the live stream."""
    http, app, base_url = relay_env
    session = await _initialize(http)

    async def change_config():
        await asyncio.sleep(0.3)  # let the stream register first
        async with AsyncClient(
            base_url=base_url, headers={"Authorization": f"Bearer {SERVICE_KEY}"}
        ) as admin:
            resp = await admin.put(
                "/api/v1/bundles/main", json={"name": "main", "description": "updated"}
            )
            assert resp.status_code == 200

    changer = asyncio.create_task(change_config())
    event = await _read_stream_until(
        http, session, lambda e: e.get("method") == "notifications/tools/list_changed"
    )
    await changer
    assert event["method"] == "notifications/tools/list_changed"


async def test_list_changed_cross_instance(relay_env, engine, redis):
    """Stream on replica B hears a change made through replica A's API."""
    http_a, app_a, base_a = relay_env
    app_b = make_app(engine, redis)
    async with running_app(app_b) as base_b:
        async with AsyncClient(
            base_url=base_b,
            headers={"Authorization": f"Bearer {ENDPOINT_KEY}"},
            timeout=10,
        ) as http_b:
            session = await _initialize(http_b)

            async def change_on_a():
                await asyncio.sleep(0.3)
                async with AsyncClient(
                    base_url=base_a, headers={"Authorization": f"Bearer {SERVICE_KEY}"}
                ) as admin:
                    resp = await admin.put(
                        "/api/v1/bundles/main",
                        json={"name": "main", "description": "changed on A"},
                    )
                    assert resp.status_code == 200

            changer = asyncio.create_task(change_on_a())
            event = await _read_stream_until(
                http_b,
                session,
                lambda e: e.get("method") == "notifications/tools/list_changed",
            )
            await changer
            assert event is not None


async def _call_sse(http, session, name, arguments, endpoint="main", req_id=2):
    """POST a tools/call with a progressToken; collect SSE events until the final result."""
    events = []
    body = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments, "_meta": {"progressToken": "pt1"}},
    }
    async with http.stream(
        "POST", f"/{endpoint}/mcp", headers={"Mcp-Session-Id": session}, json=body
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                msg = json.loads(line[6:])
                events.append(msg)
                if msg.get("id") == req_id:  # final result/error carries the id
                    break
    return events


async def test_progress_streamed_over_sse(relay_env):
    """PROT-1: progress notifications relayed, then the final result."""
    http, app, base_url = relay_env
    session = await _initialize(http)
    events = await _call_sse(http, session, "relay__slow_with_progress", {"steps": 3})

    progress = [e for e in events if e.get("method") == "notifications/progress"]
    assert len(progress) == 3
    assert progress[0]["params"]["progressToken"] == "pt1"
    assert progress[-1]["params"]["progress"] == 3
    final = events[-1]
    assert final["id"] == 2
    assert final["result"]["content"][0]["text"] == "done"


async def test_no_progress_token_uses_json(relay_env):
    """Calls without a progressToken keep the buffered JSON fast path."""
    http, app, base_url = relay_env
    session = await _initialize(http)
    resp = await http.post(
        "/main/mcp",
        headers={"Mcp-Session-Id": session},
        json={
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "relay__quick", "arguments": {"text": "hi"}},
        },
    )
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json()["result"]["content"][0]["text"] == "ok:hi"


async def test_timeout_fires_without_progress(relay_env):
    """PROT-2: a silent long call is timed out at call_timeout."""
    http, app, base_url = relay_env
    async with AsyncClient(
        base_url=base_url, headers={"Authorization": f"Bearer {SERVICE_KEY}"}
    ) as admin:
        await admin.put("/api/v1/config/call_timeout", json={"value": 0.3})
    session = await _initialize(http)

    resp = await http.post(
        "/main/mcp",
        headers={"Mcp-Session-Id": session},
        json={
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {"name": "relay__hang", "arguments": {"seconds": 5}},
        },
    )
    body = resp.json()
    assert body["error"]["message"] == "call_timeout"


async def test_progress_resets_timeout(relay_env):
    """PROT-2: progress keeps the call alive past call_timeout (reset-on-progress)."""
    http, app, base_url = relay_env
    async with AsyncClient(
        base_url=base_url, headers={"Authorization": f"Bearer {SERVICE_KEY}"}
    ) as admin:
        # Each step sleeps 0.05s, so 30 steps run 1.5s in total: past call_timeout,
        # while no single gap between progress events comes near it. The margin
        # is deliberately wide because the idle window also spans the upstream
        # connection handshake, and a loaded CI runner can stall for well over
        # a tenth of a second at any point.
        await admin.put("/api/v1/config/call_timeout", json={"value": 1.0})
    session = await _initialize(http)
    events = await _call_sse(http, session, "relay__slow_with_progress", {"steps": 30})
    final = events[-1]
    assert "error" not in final, final  # completed, not timed out
    assert final["result"]["content"][0]["text"] == "done"
    assert len([e for e in events if e.get("method") == "notifications/progress"]) == 30


async def test_cancellation_stops_call(relay_env):
    """PROT-3: notifications/cancelled aborts the in-flight call."""
    http, app, base_url = relay_env
    async with AsyncClient(
        base_url=base_url, headers={"Authorization": f"Bearer {SERVICE_KEY}"}
    ) as admin:
        await admin.put("/api/v1/config/call_timeout", json={"value": 30})
    session = await _initialize(http)

    async def cancel_soon():
        await asyncio.sleep(0.3)
        async with AsyncClient(
            base_url=base_url, headers={"Authorization": f"Bearer {ENDPOINT_KEY}"}
        ) as c:
            await c.post(
                "/main/mcp",
                headers={"Mcp-Session-Id": session},
                json={
                    "jsonrpc": "2.0",
                    "method": "notifications/cancelled",
                    "params": {"requestId": 7},
                },
            )

    canceller = asyncio.create_task(cancel_soon())
    resp = await http.post(
        "/main/mcp",
        headers={"Mcp-Session-Id": session},
        json={
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "relay__hang", "arguments": {"seconds": 30}},
        },
    )
    await canceller
    assert resp.json()["error"]["message"] == "cancelled"


async def _initialize_with_caps(http, caps, endpoint="main") -> str:
    resp = await http.post(
        f"/{endpoint}/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25", "capabilities": caps},
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.headers["mcp-session-id"]


async def test_elicitation_relayed_to_client(relay_env):
    """PROT-4/6: upstream elicit() reaches the client via the GET stream; reply routed back."""
    http, app, base_url = relay_env
    session = await _initialize_with_caps(http, {"elicitation": {}})

    # Drive the GET stream: answer the elicitation request when it arrives.
    async def responder():
        async with http.stream("GET", "/main/mcp", headers={"Mcp-Session-Id": session}) as resp:
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                msg = json.loads(line[6:])
                if msg.get("method") == "elicitation/create":
                    async with AsyncClient(
                        base_url=base_url, headers={"Authorization": f"Bearer {ENDPOINT_KEY}"}
                    ) as c:
                        await c.post(
                            "/main/mcp",
                            headers={"Mcp-Session-Id": session},
                            json={
                                "jsonrpc": "2.0",
                                "id": msg["id"],
                                "result": {"action": "accept", "content": {"value": "Ada"}},
                            },
                        )
                    return

    responder_task = asyncio.create_task(responder())
    await asyncio.sleep(0.2)  # let the stream register
    resp = await http.post(
        "/main/mcp",
        headers={"Mcp-Session-Id": session},
        json={
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {"name": "relay__ask_name", "arguments": {}},
        },
    )
    await asyncio.wait_for(responder_task, timeout=5)
    assert resp.json()["result"]["content"][0]["text"] == "hello Ada"


async def test_elicitation_from_modern_upstream_relayed_to_legacy_client(relay_env):
    """PROT-4/PROT-21: a modern upstream's input_required reaches a handshake client
    as elicitation/create on its GET stream, and the reply completes the upstream call."""
    http, app, base_url = relay_env
    session = await _initialize_with_caps(http, {"elicitation": {}})

    async def responder():
        async with http.stream("GET", "/main/mcp", headers={"Mcp-Session-Id": session}) as resp:
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                msg = json.loads(line[6:])
                if msg.get("method") == "elicitation/create":
                    async with AsyncClient(
                        base_url=base_url, headers={"Authorization": f"Bearer {ENDPOINT_KEY}"}
                    ) as c:
                        await c.post(
                            "/main/mcp",
                            headers={"Mcp-Session-Id": session},
                            json={
                                "jsonrpc": "2.0",
                                "id": msg["id"],
                                "result": {"action": "accept", "content": {"value": "Grace"}},
                            },
                        )
                    return

    responder_task = asyncio.create_task(responder())
    await asyncio.sleep(0.2)
    resp = await http.post(
        "/main/mcp",
        headers={"Mcp-Session-Id": session},
        json={
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {"name": "modern__ask_name", "arguments": {}},
        },
    )
    await asyncio.wait_for(responder_task, timeout=5)
    assert resp.json()["result"]["content"][0]["text"] == "hello Grace"


async def test_roots_relayed_to_client(relay_env):
    """PROT-4: upstream roots/list reaches the client and the reply routes back."""
    http, app, base_url = relay_env
    session = await _initialize_with_caps(http, {"roots": {}})

    async def responder():
        async with http.stream("GET", "/main/mcp", headers={"Mcp-Session-Id": session}) as resp:
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                msg = json.loads(line[6:])
                if msg.get("method") == "roots/list":
                    async with AsyncClient(
                        base_url=base_url, headers={"Authorization": f"Bearer {ENDPOINT_KEY}"}
                    ) as c:
                        await c.post(
                            "/main/mcp",
                            headers={"Mcp-Session-Id": session},
                            json={
                                "jsonrpc": "2.0",
                                "id": msg["id"],
                                "result": {"roots": [{"uri": "file:///w", "name": "w"}]},
                            },
                        )
                    return

    task = asyncio.create_task(responder())
    await asyncio.sleep(0.2)
    resp = await http.post(
        "/main/mcp",
        headers={"Mcp-Session-Id": session},
        json={
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {"name": "relay__read_roots", "arguments": {}},
        },
    )
    await asyncio.wait_for(task, timeout=5)
    assert resp.json()["result"]["content"][0]["text"] == "roots:1"


async def test_logging_relayed_to_client_stream(relay_env):
    """PROT-7: after logging/setLevel, an upstream log notification reaches the GET stream."""
    http, app, base_url = relay_env
    session = await _initialize(http)
    resp = await http.post(
        "/main/mcp",
        headers={"Mcp-Session-Id": session},
        json={"jsonrpc": "2.0", "id": 3, "method": "logging/setLevel", "params": {"level": "info"}},
    )
    assert resp.status_code == 200, resp.text

    reader = asyncio.create_task(
        _read_stream_until(http, session, lambda e: e.get("method") == "notifications/message")
    )
    await asyncio.sleep(0.2)
    await http.post(
        "/main/mcp",
        headers={"Mcp-Session-Id": session},
        json={
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {"name": "relay__emit_log", "arguments": {}},
        },
    )
    event = await reader
    assert event["method"] == "notifications/message"
    assert "hello-log" in json.dumps(event["params"])


async def test_elicitation_not_advertised_yields_error(relay_env):
    """PROT-5: without the elicitation capability the upstream request can't be served."""
    http, app, base_url = relay_env
    session = await _initialize_with_caps(http, {})  # no elicitation

    resp = await http.post(
        "/main/mcp",
        headers={"Mcp-Session-Id": session},
        json={
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "relay__ask_name", "arguments": {}},
        },
    )
    # the tool's elicit() fails (no handler) -> upstream returns an error result
    body = resp.json()
    assert body["result"]["isError"] is True


# --- modern-era clients (2026-07-28): subscriptions/listen, per-request logs, disconnect ----

MODERN = "2026-07-28"


def _modern(method, params=None, *, id_=1, log_level=None):
    """A modern-era request body and the headers that mirror it (PROT-13/15)."""
    params = dict(params or {})
    meta = {PROTOCOL_VERSION_META_KEY: MODERN, CLIENT_CAPABILITIES_META_KEY: {}}
    if log_level is not None:
        meta[LOG_LEVEL_META_KEY] = log_level
    params["_meta"] = meta
    headers = {"MCP-Protocol-Version": MODERN, "Mcp-Method": method}
    if method in NAME_BEARING_METHODS:
        headers["Mcp-Name"] = params[NAME_BEARING_METHODS[method]]
    return {"jsonrpc": "2.0", "id": id_, "method": method, "params": params}, headers


async def _listen_until(http, predicate, *, filter_, acknowledged, id_=7, timeout=5):
    """Open subscriptions/listen and return (ack, first event matching predicate).

    ``acknowledged`` is set once the acknowledgement arrived, so a test can make
    its change only when the stream is registered and cannot miss the event.
    """
    body, headers = _modern("subscriptions/listen", {"notifications": filter_}, id_=id_)

    async def reader():
        ack = None
        async with http.stream("POST", "/main/mcp", headers=headers, json=body) as resp:
            assert resp.status_code == 200, await resp.aread()
            assert resp.headers["content-type"].startswith("text/event-stream")
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                if ack is None:
                    ack = event
                    acknowledged.set()
                    continue
                if predicate(event):
                    return ack, event
        return ack, None

    return await asyncio.wait_for(reader(), timeout=timeout)


async def test_subscriptions_listen_acknowledges_and_relays_list_changed(relay_env):
    """PROT-17: the ack names only what the gateway honours; list_changed is tagged."""
    http, app, base_url = relay_env
    acknowledged = asyncio.Event()

    async def change_config():
        await asyncio.wait_for(acknowledged.wait(), timeout=5)
        async with AsyncClient(
            base_url=base_url, headers={"Authorization": f"Bearer {SERVICE_KEY}"}
        ) as admin:
            resp = await admin.put(
                "/api/v1/bundles/main", json={"name": "main", "description": "updated"}
            )
            assert resp.status_code == 200

    changer = asyncio.create_task(change_config())
    ack, event = await _listen_until(
        http,
        lambda e: e.get("method") == "notifications/tools/list_changed",
        filter_={"toolsListChanged": True, "resourceSubscriptions": ["res://x"]},
        acknowledged=acknowledged,
    )
    await changer
    assert ack["method"] == "notifications/subscriptions/acknowledged"
    assert ack["params"]["notifications"] == {"toolsListChanged": True}
    assert ack["params"]["_meta"][SUBSCRIPTION_ID_META_KEY] == 7
    assert event["params"]["_meta"][SUBSCRIPTION_ID_META_KEY] == 7


async def test_subscriptions_listen_cross_instance(relay_env, engine, redis):
    """PROT-17 + SES-13: a listen stream on replica B hears a change made through A."""
    http_a, app_a, base_a = relay_env
    app_b = make_app(engine, redis)
    async with running_app(app_b) as base_b:
        async with AsyncClient(
            base_url=base_b, headers={"Authorization": f"Bearer {ENDPOINT_KEY}"}, timeout=10
        ) as http_b:
            acknowledged = asyncio.Event()

            async def change_on_a():
                await asyncio.wait_for(acknowledged.wait(), timeout=5)
                async with AsyncClient(
                    base_url=base_a, headers={"Authorization": f"Bearer {SERVICE_KEY}"}
                ) as admin:
                    resp = await admin.put(
                        "/api/v1/bundles/main", json={"name": "main", "description": "via A"}
                    )
                    assert resp.status_code == 200

            changer = asyncio.create_task(change_on_a())
            _ack, event = await _listen_until(
                http_b,
                lambda e: e.get("method") == "notifications/tools/list_changed",
                filter_={"toolsListChanged": True},
                acknowledged=acknowledged,
            )
            await changer
            assert event is not None


async def _modern_call_events(http, name, arguments, *, log_level=None, id_=9):
    body, headers = _modern(
        "tools/call", {"name": name, "arguments": arguments}, id_=id_, log_level=log_level
    )
    events = []
    async with http.stream("POST", "/main/mcp", headers=headers, json=body) as resp:
        assert resp.status_code == 200, await resp.aread()
        assert resp.headers["content-type"].startswith("text/event-stream")
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                msg = json.loads(line[6:])
                events.append(msg)
                if msg.get("id") == id_:
                    break
    return events


async def test_modern_call_streams_logs_at_requested_level(relay_env):
    """PROT-19/PROT-20: a modern call is streamed; logs arrive on it when a level was set."""
    http, app, base_url = relay_env
    events = await _modern_call_events(http, "relay__emit_log", {}, log_level="info")
    logs = [e for e in events if e.get("method") == "notifications/message"]
    assert logs and "hello-log" in json.dumps(logs[0]["params"])
    assert events[-1]["result"]["content"][0]["text"] == "logged"
    assert events[-1]["result"]["resultType"] == "complete"


async def test_modern_call_without_log_level_gets_no_logs(relay_env):
    http, app, base_url = relay_env
    events = await _modern_call_events(http, "relay__emit_log", {})
    assert [e for e in events if e.get("method") == "notifications/message"] == []
    assert events[-1]["result"]["content"][0]["text"] == "logged"


async def test_modern_client_disconnect_cancels_the_call(relay_env):
    """PROT-19: closing the response stream cancels the upstream call and it is accounted."""
    http, app, base_url = relay_env
    body, headers = _modern("tools/call", {"name": "relay__hang", "arguments": {"seconds": 30}})
    async with http.stream("POST", "/main/mcp", headers=headers, json=body) as resp:
        assert resp.status_code == 200
        # leave without reading: the client goes away mid-call

    for _ in range(50):
        await asyncio.sleep(0.05)
        await app.state.container.audit.drain()
        async with app.state.container.session_factory() as db:
            records = (await db.execute(select(AuditRecordRow))).scalars().all()
        if any(r.tool_name == "hang" for r in records):
            break
    hang = next(r for r in records if r.tool_name == "hang")
    assert (hang.status, hang.error_message) == ("error", "cancelled")
