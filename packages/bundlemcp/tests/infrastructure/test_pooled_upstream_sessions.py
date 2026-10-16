"""Pooled upstream sessions against a real Streamable HTTP upstream (SES-4…9, SES-21, AUTH-31)."""

import asyncio

import pytest
from bundlemcp.application.contracts.upstream.upstream_session_pool import UpstreamLeaseRequest
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.response_log import ResponseLog
from bundlemcp.domain.sessions.upstream_failure import UpstreamFailure
from bundlemcp.domain.sessions.upstream_session_key import UpstreamSessionKey
from bundlemcp.infrastructure.fastmcp.client_factory import default_client_factory
from bundlemcp.infrastructure.fastmcp.pooled_upstream_sessions import (
    PooledUpstreamSessions,
    PoolLimits,
)
from fastmcp import FastMCP

from tests.conftest import hermetic_settings
from tests.loopback_upstream import RecordingUpstream, serving_upstream


class Sink:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict, str | None]] = []

    async def received(self, server, notification, *, bound_to):
        self.messages.append((server.name, notification, bound_to))


def _upstream() -> FastMCP:
    server = FastMCP("echo")

    @server.tool
    def echo(text: str) -> str:
        return f"echo:{text}"

    return server


@pytest.fixture
async def upstream():
    recording = RecordingUpstream(_upstream())
    async with serving_upstream(recording) as url:
        yield recording, url


def _pool(limits: PoolLimits | None = None, sink: Sink | None = None) -> PooledUpstreamSessions:
    settings = hermetic_settings(egress_allow_cidrs=["127.0.0.1/32"])
    pool = PooledUpstreamSessions(
        default_client_factory(settings, lambda: 16 * 1024 * 1024),
        lambda: limits or PoolLimits(total=8, per_server=8, idle_timeout=60),
        sink or Sink(),
    )
    return pool


def _server(url: str, **fields) -> McpServer:
    return McpServer(name="echo", url=url, protocol_mode="legacy", **fields)


def _request(server: McpServer, sub: str = "alice", **fields) -> UpstreamLeaseRequest:
    headers = fields.pop("headers", {})
    key = UpstreamSessionKey.for_request(
        server, sub=sub, forwarded_headers=headers, endpoint="main"
    )
    return UpstreamLeaseRequest(server=server, key=key, headers=headers, **fields)


async def _echo(pool, request, text="a") -> str:
    async with pool.lease(request) as lease:
        result = await lease.client.call_tool_mcp("echo", {"text": text})
        return result.content[0].text


async def test_ses6_a_second_call_reuses_the_pooled_session(upstream):
    """SES-6: two unbound calls on one replica cost one initialize."""
    recording, url = upstream
    pool = _pool()
    server = _server(url, send_identity_header=False)
    assert await _echo(pool, _request(server)) == "echo:a"
    assert await _echo(pool, _request(server, sub="bob")) == "echo:a"
    assert recording.initializes() == 1
    sessions = {call.session_id for call in recording.calls("tools/call")}
    assert len(sessions) == 1
    await pool.close()


async def test_auth31_per_request_credentials_are_injected_on_one_session(upstream):
    """AUTH-31: one pooled session sends each request with that request's own credentials."""
    recording, url = upstream
    pool = _pool()
    server = _server(url, forward_headers={"authorization": "authorization"})
    headers = {"authorization": "Bearer caller"}
    for minted in ("Bearer one", "Bearer two"):
        request = _request(server, headers=headers, credentials={"x-upstream-token": minted})
        await _echo(pool, request)
    sent = [call.headers.get("x-upstream-token") for call in recording.calls("tools/call")]
    assert sent == ["Bearer one", "Bearer two"]
    assert recording.initializes() == 1
    await pool.close()


async def test_auth31_two_callers_get_two_sessions(upstream):
    """AUTH-31: callers with different forwarded headers never share an upstream session."""
    recording, url = upstream
    pool = _pool()
    server = _server(url, forward_headers={"authorization": "authorization"})
    await _echo(pool, _request(server, "alice", headers={"authorization": "Bearer a"}))
    await _echo(pool, _request(server, "bob", headers={"authorization": "Bearer b"}))
    by_session = {
        call.session_id: call.headers.get("authorization") for call in recording.calls("tools/call")
    }
    assert sorted(by_session.values()) == ["Bearer a", "Bearer b"]
    assert recording.initializes() == 2
    await pool.close()


async def test_ses5_another_replica_continues_a_bound_session_without_initialize(upstream):
    """SES-5: the binding is all a second replica needs to continue the upstream session."""
    recording, url = upstream
    server = _server(url, send_identity_header=False)
    first, second = _pool(), _pool()
    async with first.lease(_request(server, bound_to="s1")) as lease:
        await lease.client.call_tool_mcp("echo", {"text": "a"})
        binding = lease.binding
    assert binding is not None and binding.upstream_session_id is not None
    async with second.lease(_request(server, bound_to="s1", binding=binding)) as lease:
        result = await lease.client.call_tool_mcp("echo", {"text": "b"})
        assert lease.binding == binding
    assert result.content[0].text == "echo:b"
    assert recording.initializes() == 1
    assert {call.session_id for call in recording.calls("tools/call")} == {
        binding.upstream_session_id
    }
    await first.close()
    await second.close()


async def test_ses5_closing_a_transport_keeps_the_upstream_session(upstream):
    """SES-5: losing the connection does not end a bound upstream session."""
    recording, url = upstream
    server = _server(url, send_identity_header=False)
    pool = _pool()
    async with pool.lease(_request(server, bound_to="s1")) as lease:
        binding = lease.binding
    await pool.close()
    assert recording.deletes() == []
    await _echo(_pool(), _request(server, bound_to="s1", binding=binding))
    assert recording.initializes() == 1


async def test_ses4_ending_a_binding_deletes_its_upstream_session(upstream):
    """SES-4: the upstream receives DELETE for the bound session when it is ended."""
    recording, url = upstream
    server = _server(url, send_identity_header=False)
    pool = _pool()
    async with pool.lease(_request(server, bound_to="s1")) as lease:
        binding = lease.binding
    await pool.end(server, binding, {})
    assert [call.session_id for call in recording.deletes()] == [binding.upstream_session_id]
    assert pool.held == []
    await pool.close()


async def test_ses7_a_forgotten_session_is_reported_as_expired(upstream):
    """SES-7: a 404 for the bound session classifies as an expired session."""
    recording, url = upstream
    server = _server(url, send_identity_header=False)
    pool = _pool()
    async with pool.lease(_request(server, bound_to="s1")) as lease:
        binding = lease.binding
    await pool.close()
    recording.forget()
    responses = ResponseLog()
    with pytest.raises(Exception):  # noqa: B017 - the SDK's own error type
        async with _pool().lease(
            _request(server, bound_to="s1", binding=binding, responses=responses)
        ) as lease:
            await lease.client.call_tool_mcp("echo", {"text": "a"})
    assert UpstreamFailure.of(responses, jsonrpc_code=None) is UpstreamFailure.SESSION_EXPIRED
    fresh = _pool()
    async with fresh.lease(_request(server, bound_to="s1", binding=binding, fresh=True)) as lease:
        await lease.client.call_tool_mcp("echo", {"text": "b"})
        assert lease.binding.upstream_session_id != binding.upstream_session_id
    await fresh.close()


async def test_ses7_an_unreachable_upstream_is_not_sent():
    """SES-7: a refused connection means the request never reached the upstream."""
    from tests.loopback_upstream import free_port

    server = _server(f"http://127.0.0.1:{free_port()}/mcp", send_identity_header=False)
    responses = ResponseLog()
    with pytest.raises(Exception):  # noqa: B017
        async with _pool().lease(_request(server, responses=responses)) as lease:
            await lease.client.call_tool_mcp("echo", {"text": "a"})
    assert UpstreamFailure.of(responses, jsonrpc_code=None) is UpstreamFailure.NOT_SENT


async def test_ses8_identity_free_sessions_are_evicted_first(upstream):
    """SES-8: at the cap the idle shared session goes, the idle identity-bound one stays."""
    _recording, url = upstream
    pool = _pool(PoolLimits(total=2, per_server=8, idle_timeout=60))
    shared = _server(url, send_identity_header=False)
    bound = shared.model_copy(update={"name": "crm", "send_identity_header": True})
    await _echo(pool, _request(shared))
    await _echo(pool, _request(bound, "alice"))
    await _echo(pool, _request(bound, "bob"))
    held = sorted((session.key.server_name, session.key.is_shared) for session in pool.held)
    assert held == [("crm", False), ("crm", False)]
    await pool.close()


async def test_ses8_nothing_evictable_serves_the_call_on_its_own_connection(upstream):
    """SES-8: with every session in use at the cap, a call still succeeds and is not kept."""
    _recording, url = upstream
    pool = _pool(PoolLimits(total=1, per_server=1, idle_timeout=60))
    server = _server(url, send_identity_header=False)
    async with pool.lease(_request(server)) as held:
        assert await _echo(pool, _request(server), "b") == "echo:b"
        await held.client.call_tool_mcp("echo", {"text": "a"})
    assert len(pool.held) == 1
    await pool.close()


async def test_ses8_idle_sessions_close_after_the_timeout(upstream):
    """SES-8: an unused shared session is closed and ended upstream once it idles out."""
    recording, url = upstream
    pool = _pool(PoolLimits(total=8, per_server=8, idle_timeout=0.1))
    pool.start()
    await _echo(pool, _request(_server(url, send_identity_header=False)))
    for _ in range(50):
        if not pool.held and recording.deletes():
            break
        await asyncio.sleep(0.05)
    assert pool.held == []
    assert len(recording.deletes()) == 1
    await pool.close()


async def test_ses21_invalidation_closes_a_servers_idle_transports(upstream):
    """SES-21: a server event closes its idle transports; the next call opens a new session."""
    recording, url = upstream
    pool = _pool()
    server = _server(url, send_identity_header=False)
    await _echo(pool, _request(server))
    await pool.invalidate("echo")
    assert pool.held == []
    await _echo(pool, _request(server))
    assert recording.initializes() == 2
    await pool.close()


async def test_ses9_a_leased_session_closes_when_its_call_ends(upstream):
    """SES-9: a session in use when the server changes is not reused after its call."""
    recording, url = upstream
    pool = _pool()
    server = _server(url, send_identity_header=False)
    async with pool.lease(_request(server)) as lease:
        await pool.invalidate_all()
        await lease.client.call_tool_mcp("echo", {"text": "a"})
    assert pool.held == []
    await _echo(pool, _request(server))
    assert recording.initializes() == 2
    await pool.close()
