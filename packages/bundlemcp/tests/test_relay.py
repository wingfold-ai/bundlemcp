"""Protocol-relay tests (spec 32): GET stream, list_changed, progress, cancel, elicitation.

SSE streaming can't go through httpx's ASGITransport (it buffers the whole
response), so these tests run the gateway on a real loopback uvicorn server —
still hermetic (no Docker, no external network; the upstream is in-process
FastMCP via the injected client factory).
"""

import asyncio
import contextlib
import json
import socket

import pytest
import uvicorn
from bundlemcp.api.app import create_app
from bundlemcp.models import (
    ApiKey,
    ApiKeyKind,
    Bundle,
    BundleServer,
    Endpoint,
    McpServer,
    Tool,
)
from bundlemcp.security import API_KEY_PREFIX, display_prefix, generate_token, hash_token
from bundlemcp.settings import Settings
from bundlemcp.store import session_factory
from fakeredis.aioredis import FakeRedis
from fastmcp import Client, FastMCP
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

SERVICE_KEY = generate_token(API_KEY_PREFIX)
ENDPOINT_KEY = generate_token(API_KEY_PREFIX)

# --- in-process upstream with slow/progress tools ----------------------------

relay_server = FastMCP("relay")


@relay_server.tool
async def quick(text: str) -> str:
    """Fast tool."""
    return f"ok:{text}"


@relay_server.tool
async def slow_with_progress(steps: int, ctx=None) -> str:
    """Reports progress each step."""
    from fastmcp import Context

    assert isinstance(ctx, Context)
    for i in range(steps):
        await ctx.report_progress(progress=i + 1, total=steps)
        await asyncio.sleep(0.05)
    return "done"


@relay_server.tool
async def hang(seconds: float) -> str:
    """Sleeps without progress (timeout/cancel target)."""
    await asyncio.sleep(seconds)
    return "finished"


def upstream_factory(server, extra_headers):
    return Client(relay_server)


async def seed(engine: AsyncEngine) -> None:
    factory = session_factory(engine)
    async with factory() as db:
        db.add_all(
            [
                ApiKey(
                    name="svc",
                    key_hash=hash_token(SERVICE_KEY),
                    key_prefix=display_prefix(SERVICE_KEY),
                    kind=ApiKeyKind.SERVICE,
                ),
                ApiKey(
                    name="ep",
                    key_hash=hash_token(ENDPOINT_KEY),
                    key_prefix=display_prefix(ENDPOINT_KEY),
                    kind=ApiKeyKind.ENDPOINT,
                ),
            ]
        )
        srv = McpServer(name="relay", url="http://relay/mcp")
        bundle = Bundle(name="main")
        db.add_all([srv, bundle])
        await db.commit()
        await db.refresh(srv)
        await db.refresh(bundle)
        db.add(BundleServer(bundle_id=bundle.id, server_id=srv.id))
        db.add(Endpoint(name="main", bundle_id=bundle.id, auth_modes=["api_key"]))
        for tool in ("quick", "slow_with_progress", "hang"):
            db.add(Tool(server_id=srv.id, name=tool, schema_hash="h", input_schema={}))
        await db.commit()


def make_app(engine, redis):
    settings = Settings(_env_file=None, database_url="sqlite+aiosqlite://")
    return create_app(settings, engine=engine, redis=redis, client_factory=upstream_factory)


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
