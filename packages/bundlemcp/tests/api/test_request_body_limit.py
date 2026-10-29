"""The request body limit on the MCP endpoints, the management API and /oauth/ (SEC-7, EP-9)."""

import asyncio
import json
from contextlib import contextmanager

import pytest
from bundlemcp.domain.config.runtime_settings import MIB
from sqlalchemy import event

from tests.conftest import SERVICE_KEY, seed_api_key, serving

LIMIT = 4 * MIB


@contextmanager
def statements(engine):
    """Every SQL statement the engine runs inside the block."""
    seen: list[str] = []

    def record(conn, cursor, statement, *args):
        seen.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)


def rpc_body(size: int) -> bytes:
    """A JSON-RPC request padded to ``size`` bytes."""
    head = b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"pad":"'
    tail = b'"}}'
    return head + b"x" * (size - len(head) - len(tail)) + tail


async def chunks(body: bytes, size: int = 256 * 1024):
    for start in range(0, len(body), size):
        yield body[start : start + size]


@pytest.fixture
async def app_client(engine, redis):
    await seed_api_key(engine, SERVICE_KEY)
    async with serving(engine, redis, bearer=SERVICE_KEY) as (http, app):
        yield http, app


async def test_ep9_declared_oversized_mcp_request_is_refused_before_admission(app_client, engine):
    """EP-9/SEC-7: a declared length over the limit is a JSON-RPC 413, with no database work."""
    http, _ = app_client
    with statements(engine) as seen:
        resp = await http.post(
            "/main/mcp",
            content=rpc_body(LIMIT + 1),
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 413
    body = resp.json()
    assert body["jsonrpc"] == "2.0" and body["id"] is None
    assert body["error"]["code"] == -32600
    assert str(LIMIT) in body["error"]["message"]
    assert seen == []


async def test_ep9_chunked_oversized_mcp_request_is_refused(app_client, engine):
    """EP-9/SEC-7: a body without Content-Length is refused once it crosses the limit."""
    http, _ = app_client
    with statements(engine) as seen:
        resp = await http.post(
            "/main/mcp",
            content=chunks(rpc_body(LIMIT + 1)),
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == -32600
    assert seen == []


async def test_sec7_a_body_at_the_limit_reaches_the_endpoint(app_client):
    """SEC-7: a body of exactly the limit is not refused for its size."""
    http, _ = app_client
    for content in (rpc_body(LIMIT), chunks(rpc_body(LIMIT))):
        resp = await http.post(
            "/nope/mcp", content=content, headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 404  # admitted past the limit, then the unknown endpoint


@pytest.mark.parametrize("chunked", [False, True], ids=["declared", "chunked"])
async def test_sec7_management_api_request_over_the_limit(app_client, chunked):
    """SEC-7: /api/v1 answers 413 with its error object and changes nothing."""
    http, _ = app_client
    payload = json.dumps({"name": "main", "description": "x" * (LIMIT + 1)}).encode()
    resp = await http.put(
        "/api/v1/bundles/huge",
        content=chunks(payload) if chunked else payload,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 413
    assert "limit" in resp.json()["detail"]
    assert (await http.get("/api/v1/bundles/huge")).status_code == 404


async def test_sec7_limit_changed_at_runtime(app_client):
    """SEC-7: a lowered limit applies once the configuration change has propagated."""
    http, app = app_client
    resp = await http.put("/api/v1/config/max_request_bytes", json={"value": 1 * MIB})
    assert resp.status_code == 200
    config = app.state.container.runtime_config
    for _ in range(100):
        if config.snapshot.max_request_bytes == 1 * MIB:
            break
        await asyncio.sleep(0.01)
    resp = await http.post(
        "/main/mcp",
        content=chunks(rpc_body(int(1.5 * MIB))),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 413


OAUTH_LIMIT = 64 * 1024


def registration_body(size: int) -> bytes:
    """A client registration padded to ``size`` bytes."""
    head = b'{"redirect_uris":["https://c.example/cb"],"client_name":"'
    tail = b'"}'
    return head + b"x" * (size - len(head) - len(tail)) + tail


async def _stored_clients(engine) -> int:
    from bundlemcp.infrastructure.postgres.rows.oauth_client_row import OAuthClientRow
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import AsyncSession

    async with AsyncSession(engine) as db:
        return (await db.execute(select(func.count()).select_from(OAuthClientRow))).scalar_one()


async def test_sec7_oauth_register_declared_length_over_limit(app_client, engine):
    """SEC-7: a declared registration body over 64 KiB is a 413 in the OAuth error shape,
    refused before it is parsed, and registers no client."""
    http, _ = app_client
    with statements(engine) as seen:
        resp = await http.post(
            "/oauth/register",
            content=registration_body(100 * 1024),
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 413
    body = resp.json()
    assert body["error"] == "invalid_request"
    assert str(OAUTH_LIMIT) in body["error_description"]
    assert seen == []
    assert await _stored_clients(engine) == 0


async def test_sec7_oauth_chunked_body_over_limit(app_client, engine):
    """SEC-7: a streamed registration body without Content-Length is refused once it crosses
    64 KiB, in the OAuth error shape, and registers no client."""
    http, _ = app_client
    resp = await http.post(
        "/oauth/register",
        content=chunks(registration_body(100 * 1024), size=16 * 1024),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 413
    assert resp.json()["error"] == "invalid_request"
    assert await _stored_clients(engine) == 0


async def test_sec7_oauth_limit_ignores_runtime_limit(app_client):
    """SEC-7: raising the runtime request limit does not raise the fixed /oauth/ limit."""
    http, app = app_client
    resp = await http.put("/api/v1/config/max_request_bytes", json={"value": 16 * MIB})
    assert resp.status_code == 200
    config = app.state.container.runtime_config
    for _ in range(100):
        if config.snapshot.max_request_bytes == 16 * MIB:
            break
        await asyncio.sleep(0.01)
    assert config.snapshot.max_request_bytes == 16 * MIB
    form = b"grant_type=refresh_token&refresh_token=" + b"x" * (100 * 1024)
    resp = await http.post(
        "/oauth/token",
        content=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 413
    assert resp.json()["error"] == "invalid_request"


async def test_sec7_oauth_body_under_limit_reaches_route(app_client):
    """SEC-7: a registration body under 64 KiB is not refused for its size."""
    http, _ = app_client
    resp = await http.post(
        "/oauth/register",
        content=registration_body(OAUTH_LIMIT),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code != 413
