"""The modern-era edge (MCP 2026-07-28, spec 32 PROT-13..16): stateless requests on the
same endpoint that still serves the initialize handshake.

ASGI-transport style like test_gateway: the upstream is an in-process FastMCP
server behind the injected client factory.
"""

import json
from contextlib import asynccontextmanager
from typing import Any

import pytest
from bundlemcp.api.app import create_app
from bundlemcp.api.composition_overrides import CompositionOverrides
from bundlemcp.crypto import API_KEY_PREFIX, display_prefix, generate_token, hash_token
from bundlemcp.models import (
    ApiKey,
    ApiKeyKind,
    Bundle,
    BundleServer,
    Endpoint,
    McpServer,
    Tool,
)
from bundlemcp.settings import Settings
from bundlemcp.store import session_factory
from fakeredis.aioredis import FakeRedis
from fastmcp import Client, FastMCP
from httpx import ASGITransport, AsyncClient
from mcp.shared.inbound import NAME_BEARING_METHODS
from mcp.types import (
    CLIENT_CAPABILITIES_META_KEY,
    CLIENT_INFO_META_KEY,
    HEADER_MISMATCH,
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    PROTOCOL_VERSION_META_KEY,
    SERVER_INFO_META_KEY,
    UNSUPPORTED_PROTOCOL_VERSION,
)
from sqlalchemy.ext.asyncio import AsyncEngine

ENDPOINT_KEY = generate_token(API_KEY_PREFIX)
MODERN = "2026-07-28"

REGION_SCHEMA = {
    "type": "object",
    "properties": {
        "region": {"type": "string", "x-mcp-header": "Region"},
        "query": {"type": "string"},
    },
    "required": ["region", "query"],
}

echo_server = FastMCP("echo")


@echo_server.tool
def say(text: str) -> str:
    """Echo the text."""
    return f"echo:{text}"


@echo_server.tool
def run_query(region: str, query: str) -> str:
    """A tool whose region argument is mirrored into an HTTP header."""
    return f"{region}:{query}"


@echo_server.resource("res://greeting")
def greeting_resource() -> str:
    """A static resource."""
    return "hello resource"


def upstream_factory(server, extra_headers, **handlers):
    return Client(echo_server, mode=server.protocol_mode, **handlers)


async def _seed(engine: AsyncEngine) -> None:
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
        bundle = Bundle(name="main", description="Use these tools wisely")
        db.add_all([echo, bundle])
        await db.commit()
        await db.refresh(echo)
        await db.refresh(bundle)
        db.add_all(
            [
                BundleServer(bundle_id=bundle.id, server_id=echo.id),
                Endpoint(name="main", bundle_id=bundle.id, auth_modes=["api_key"]),
                Tool(server_id=echo.id, name="say", schema_hash="h", input_schema={}),
                Tool(
                    server_id=echo.id, name="run_query", schema_hash="h", input_schema=REGION_SCHEMA
                ),
            ]
        )
        await db.commit()


@asynccontextmanager
async def _running(engine, redis, **settings_extra):
    await _seed(engine)
    settings = Settings(_env_file=None, database_url="sqlite+aiosqlite://", **settings_extra)
    app = create_app(
        settings,
        overrides=CompositionOverrides(engine=engine, redis=redis, client_factory=upstream_factory),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://gw",
        headers={"Authorization": f"Bearer {ENDPOINT_KEY}"},
    ) as http:
        async with app.router.lifespan_context(app):
            yield http


@pytest.fixture
async def http(engine: AsyncEngine, redis: FakeRedis):
    async with _running(engine, redis) as client:
        yield client


def _envelope(
    method: str,
    params: dict[str, Any] | None = None,
    *,
    id_: int = 1,
    version: str = MODERN,
    capabilities: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """A modern-era request body and the HTTP headers that mirror it (PROT-15)."""
    params = dict(params or {})
    params["_meta"] = {
        PROTOCOL_VERSION_META_KEY: version,
        CLIENT_CAPABILITIES_META_KEY: capabilities or {},
        CLIENT_INFO_META_KEY: {"name": "test-client", "version": "1"},
    }
    headers = {"MCP-Protocol-Version": version, "Mcp-Method": method}
    if method in NAME_BEARING_METHODS:
        headers["Mcp-Name"] = params[NAME_BEARING_METHODS[method]]
    return {"jsonrpc": "2.0", "id": id_, "method": method, "params": params}, headers


async def _modern(http, method, params=None, *, headers_override=None, **kw):
    body, headers = _envelope(method, params, **kw)
    if headers_override is not None:
        headers.update(headers_override)
    return await http.post("/main/mcp", json=body, headers=headers)


def _message(resp) -> dict[str, Any]:
    """The JSON-RPC message in a response: a JSON body, or the last event of an SSE body.

    A modern tools/call is always streamed (PROT-19); the ASGI transport buffers
    the whole stream, so the final event is the message.
    """
    if resp.headers["content-type"].startswith("text/event-stream"):
        data = [line[6:] for line in resp.text.splitlines() if line.startswith("data: ")]
        return json.loads(data[-1])
    return resp.json()


async def test_discover_advertises_versions_capabilities_and_hints(http):
    """PROT-14/PROT-16: server/discover needs no session and carries every modern field."""
    resp = await _modern(http, "server/discover")
    assert resp.status_code == 200, resp.text
    assert "mcp-session-id" not in resp.headers
    result = resp.json()["result"]
    assert result["supportedVersions"] == [MODERN]
    assert result["capabilities"]["tools"] == {"listChanged": True}
    assert result["instructions"] == "Use these tools wisely"
    assert result["resultType"] == "complete"
    assert result["_meta"][SERVER_INFO_META_KEY]["name"] == "bundlemcp/main"
    assert result["ttlMs"] == 300000 and result["cacheScope"] == "public"


async def test_tools_list_is_stateless_and_cacheable(http):
    """PROT-13/PROT-16: no initialize, no session id; the list carries cache hints."""
    resp = await _modern(http, "tools/list")
    assert resp.status_code == 200, resp.text
    result = resp.json()["result"]
    assert [t["name"] for t in result["tools"]] == ["echo__run_query", "echo__say"]
    assert result["resultType"] == "complete"
    assert result["ttlMs"] == 300000 and result["cacheScope"] == "public"
    assert result["tools"][0]["inputSchema"] == REGION_SCHEMA  # x-mcp-header passes through


async def test_tools_call_returns_shaped_result(http):
    resp = await _modern(http, "tools/call", {"name": "echo__say", "arguments": {"text": "hi"}})
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/event-stream")  # PROT-19
    result = _message(resp)["result"]
    assert result["content"][0]["text"] == "echo:hi"
    assert result["resultType"] == "complete"
    assert result["_meta"][SERVER_INFO_META_KEY]["name"] == "bundlemcp/main"


async def test_request_without_envelope_or_session_is_400(http):
    """PROT-13: neither era's opening — a dual-era client falls back on this answer."""
    resp = await http.post(
        "/main/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    )
    assert resp.status_code == 400
    err = resp.json()["error"]
    assert err["code"] == INVALID_PARAMS
    assert MODERN in err["data"]["supported"] and "2025-11-25" in err["data"]["supported"]


async def test_unknown_modern_version_is_rejected_with_supported_list(http):
    resp = await _modern(http, "tools/list", version="2099-01-01")
    assert resp.status_code == 400
    err = resp.json()["error"]
    assert err["code"] == UNSUPPORTED_PROTOCOL_VERSION
    assert err["data"] == {"supported": [MODERN], "requested": "2099-01-01"}


async def test_header_body_mismatch_is_rejected(http):
    """PROT-15: Mcp-Method must agree with the body."""
    resp = await _modern(http, "tools/list", headers_override={"Mcp-Method": "tools/call"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == HEADER_MISMATCH


async def test_mcp_param_header_validated_against_arguments(http):
    """PROT-15: an x-mcp-header argument must match its Mcp-Param-* header."""
    params = {"name": "echo__run_query", "arguments": {"region": "eu", "query": "q"}}
    wrong = await _modern(http, "tools/call", params, headers_override={"Mcp-Param-Region": "us"})
    assert wrong.status_code == 400
    assert wrong.json()["error"]["code"] == HEADER_MISMATCH

    right = await _modern(http, "tools/call", params, headers_override={"Mcp-Param-Region": "eu"})
    assert right.status_code == 200, right.text
    assert _message(right)["result"]["content"][0]["text"] == "eu:q"


async def test_get_and_delete_without_session_are_405(http):
    """EP-1: the modern era is POST-only."""
    assert (await http.get("/main/mcp")).status_code == 405
    assert (await http.delete("/main/mcp")).status_code == 405


async def test_handshake_only_methods_are_not_found_in_modern_era(http):
    """PROT-8/PROT-20: ping and logging/setLevel do not exist at 2026-07-28."""
    for method in ("ping", "logging/setLevel"):
        resp = await _modern(http, method)
        assert resp.status_code == 404, method
        assert resp.json()["error"]["code"] == METHOD_NOT_FOUND


async def test_resource_not_found_uses_invalid_params(http):
    """PROT-16: -32602 for a modern client (handshake clients keep -32002)."""
    resp = await _modern(http, "resources/read", {"uri": "res://missing"})
    assert resp.json()["error"]["code"] == INVALID_PARAMS


async def test_resources_read_forwards_a_result_with_hints(http):
    resp = await _modern(http, "resources/read", {"uri": "res://greeting"})
    assert resp.status_code == 200, resp.text
    result = resp.json()["result"]
    assert result["contents"][0]["text"] == "hello resource"
    assert "ttlMs" in result and result["cacheScope"] in ("public", "private")


async def test_handshake_clients_are_served_unchanged_on_the_same_endpoint(http):
    """PROT-13: initialize still opens a session, and its results carry no modern fields."""
    init = await http.post(
        "/main/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25", "capabilities": {}},
        },
    )
    assert init.status_code == 200, init.text
    session = init.headers["mcp-session-id"]
    listed = await http.post(
        "/main/mcp",
        headers={"Mcp-Session-Id": session},
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    result = listed.json()["result"]
    assert "resultType" not in result and "ttlMs" not in result and "_meta" not in result


async def test_legacy_protocol_can_be_switched_off(engine, redis):
    """PROT-13: with the handshake era disabled, initialize names the modern versions."""
    async with _running(engine, redis, legacy_protocol_enabled=False) as http:
        init = await http.post(
            "/main/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-11-25", "capabilities": {}},
            },
        )
        err = init.json()["error"]
        assert err["code"] == INVALID_PARAMS
        assert MODERN in err["message"]
        assert (await _modern(http, "tools/list")).status_code == 200
