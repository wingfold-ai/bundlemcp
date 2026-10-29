"""Calls on pooled upstream sessions through the composed gateway (SES-4…7, AUTH-31)."""

import asyncio

import pytest
from bundlemcp.application.metering.meter_decision import MeterDecision
from bundlemcp.domain.access.api_key_kind import ApiKeyKind
from bundlemcp.domain.shared.secrets import display_prefix, hash_token
from bundlemcp.domain.shared.system_clock import SystemClock
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.api_key_row import ApiKeyRow
from bundlemcp.infrastructure.postgres.rows.audit_record_row import AuditRecordRow
from bundlemcp.infrastructure.postgres.rows.bundle_row import BundleRow
from bundlemcp.infrastructure.postgres.rows.bundle_server_row import BundleServerRow
from bundlemcp.infrastructure.postgres.rows.endpoint_row import EndpointRow
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.postgres.rows.tool_row import ToolRow
from bundlemcp.infrastructure.valkey.session_store import ValkeySessionStore
from fastmcp import FastMCP
from sqlmodel import select

from tests.conftest import ENDPOINT_KEY, SERVICE_KEY, hermetic_settings, seed_api_key, serving
from tests.loopback_upstream import RecordingUpstream, free_port, serving_upstream

SAY = {"name": "echo__say", "arguments": {"text": "hi"}}


class CountingHook:
    def __init__(self) -> None:
        self.pre_calls = 0
        self.post_calls = 0

    async def pre_call(self, ctx):
        self.pre_calls += 1
        return MeterDecision(allowed=True)

    async def post_call(self, ctx, outcome, duration_ms):
        self.post_calls += 1


def _echo() -> FastMCP:
    server = FastMCP("echo")

    @server.tool
    def say(text: str) -> str:
        return f"said:{text}"

    return server


async def _seed(engine, url: str, static_headers: dict[str, str] | None = None) -> None:
    async with session_factory(engine)() as db:
        db.add(
            ApiKeyRow(
                name="k",
                key_hash=hash_token(ENDPOINT_KEY),
                key_prefix=display_prefix(ENDPOINT_KEY),
                kind=ApiKeyKind.ENDPOINT,
            )
        )
        server = McpServerRow(
            name="echo", url=url, protocol_mode="legacy", static_headers=static_headers or {}
        )
        bundle = BundleRow(name="main")
        db.add_all([server, bundle])
        await db.commit()
        await db.refresh(server)
        await db.refresh(bundle)
        db.add(BundleServerRow(bundle_id=bundle.id, server_id=server.id))
        db.add(EndpointRow(name="main", bundle_id=bundle.id, auth_modes=["api_key"]))
        db.add(ToolRow(server_id=server.id, name="say", schema_hash="h", input_schema={}))
        await db.commit()


def _sessions(redis) -> ValkeySessionStore:
    """The session records the gateway under test wrote, read back directly."""
    return ValkeySessionStore(redis, clock=SystemClock())


def _settings():
    return hermetic_settings(
        egress_allow_cidrs=["127.0.0.1/32"],
        discovery_refresh_interval=0,
        upstream_pooling_enabled=True,
    )


@pytest.fixture
async def upstream(engine):
    recording = RecordingUpstream(_echo())
    async with serving_upstream(recording) as url:
        await _seed(engine, url)
        yield recording


async def _initialize(http) -> str:
    resp = await http.post(
        "/main/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25", "capabilities": {}},
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.headers["mcp-session-id"]


async def _call(http, session_id: str, id_: int = 2):
    resp = await http.post(
        "/main/mcp",
        headers={"Mcp-Session-Id": session_id},
        json={"jsonrpc": "2.0", "id": id_, "method": "tools/call", "params": SAY},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_ses5_ses6_two_replicas_continue_one_upstream_session(engine, redis, upstream):
    """SES-5, SES-6: the binding lets a second replica continue the session without initialize."""
    settings = _settings()
    async with serving(engine, redis, settings=settings, bearer=ENDPOINT_KEY) as (a, _):
        async with serving(engine, redis, settings=settings, bearer=ENDPOINT_KEY) as (b, _):
            session_id = await _initialize(a)
            first = await _call(a, session_id)
            second = await _call(b, session_id, id_=3)
    assert first["result"]["content"][0]["text"] == "said:hi"
    assert second["result"]["content"][0]["text"] == "said:hi"
    assert upstream.initializes() == 1
    sent = {call.session_id for call in upstream.calls("tools/call")}
    assert len(sent) == 1
    record = await _sessions(redis).load(session_id)
    assert record is not None
    binding = record.bindings["echo"]
    assert binding.upstream_session_id == sent.pop()
    assert binding.config_fingerprint is not None and binding.protocol_version is not None


async def test_ses7_an_upstream_restart_between_calls_is_invisible(engine, redis, upstream):
    """SES-7: a 404 re-initializes, rebinds and retries under one pre_call and one post_call."""
    hook = CountingHook()
    settings = _settings()
    async with serving(
        engine, redis, settings=settings, bearer=ENDPOINT_KEY, metering_hook=hook
    ) as (http, _):
        session_id = await _call_after_initialize(http)
        before = (await _sessions(redis).load(session_id)).bindings["echo"]
        upstream.forget()
        hook.pre_calls = hook.post_calls = 0
        result = await _call(http, session_id, id_=3)
    assert result["result"]["content"][0]["text"] == "said:hi"
    assert (hook.pre_calls, hook.post_calls) == (1, 1)
    assert upstream.initializes() == 2
    after = (await _sessions(redis).load(session_id)).bindings["echo"]
    assert after.upstream_session_id != before.upstream_session_id


async def _call_after_initialize(http) -> str:
    session_id = await _initialize(http)
    await _call(http, session_id)
    return session_id


async def test_ses7_a_repeated_failure_is_an_error_and_audited(engine, redis, upstream):
    """SES-7: when the retry fails too the client gets -32000 and the audit says error."""
    upstream.amnesiac = True
    async with serving(engine, redis, settings=_settings(), bearer=ENDPOINT_KEY) as (http, app):
        session_id = await _initialize(http)
        result = await _call(http, session_id)
        await app.state.container.audit.drain()
        async with app.state.container.session_factory() as db:
            records = (await db.execute(select(AuditRecordRow))).scalars().all()
    assert result["error"]["code"] == -32000
    assert [record.status for record in records] == ["error"]
    assert upstream.initializes() == 2  # the first session, and the one retry opened


async def test_ses7_an_unreachable_upstream_is_an_error(engine, redis):
    """SES-7: a refused connection is answered -32000 and audited as an error."""
    await _seed(engine, f"http://127.0.0.1:{free_port()}/mcp")
    async with serving(engine, redis, settings=_settings(), bearer=ENDPOINT_KEY) as (http, app):
        result = await _call(http, await _initialize(http))
        await app.state.container.audit.drain()
        async with app.state.container.session_factory() as db:
            records = (await db.execute(select(AuditRecordRow))).scalars().all()
    assert result["error"]["code"] == -32000
    assert [record.status for record in records] == ["error"]


async def test_ses4_ending_the_session_ends_its_upstream_sessions(engine, redis, upstream):
    """SES-4: DELETE on the endpoint sends DELETE for every bound upstream session."""
    async with serving(engine, redis, settings=_settings(), bearer=ENDPOINT_KEY) as (http, _):
        session_id = await _call_after_initialize(http)
        bound = (await _sessions(redis).load(session_id)).bindings["echo"]
        resp = await http.request("DELETE", "/main/mcp", headers={"Mcp-Session-Id": session_id})
    assert resp.status_code == 204
    assert [call.session_id for call in upstream.deletes()] == [bound.upstream_session_id]


async def test_ses9_ses21_ups6_a_header_change_closes_another_replicas_transports(engine, redis):
    """SES-9, SES-21, UPS-6: a change through A ends B's session; B's next call uses it."""
    recording = RecordingUpstream(_echo())
    async with serving_upstream(recording) as url:
        await _seed(engine, url, {"x-tenant": "a"})
        await seed_api_key(engine, SERVICE_KEY, name="svc")
        settings = _settings()
        async with serving(engine, redis, settings=settings, bearer=SERVICE_KEY) as (a, _):
            async with serving(engine, redis, settings=settings, bearer=ENDPOINT_KEY) as (b, _):
                session_id = await _call_after_initialize(b)
                first = (await _sessions(redis).load(session_id)).bindings["echo"]
                resp = await a.put(
                    "/api/v1/upstreams/echo",
                    json={
                        "name": "echo",
                        "url": url,
                        "protocol_mode": "session",
                        "static_headers": {"x-tenant": "b"},
                    },
                )
                assert resp.status_code == 200, resp.text
                for _ in range(40):  # the propagation budget is 2 seconds
                    if recording.deletes():
                        break
                    await asyncio.sleep(0.05)
                assert [d.session_id for d in recording.deletes()] == [first.upstream_session_id]
                await _call(b, session_id, id_=3)
        rebound = (await _sessions(redis).load(session_id)).bindings["echo"]
    calls = recording.calls("tools/call")
    assert [call.headers.get("x-tenant") for call in calls] == ["a", "b"]
    assert rebound.upstream_session_id == calls[-1].session_id != first.upstream_session_id
