"""Seeing below the MCP client: what an upstream actually answered (UPS-12, UPS-28, UPS-34)."""

import httpx2
import pytest
from bundlemcp.application.discovery.connection_diagnoser import ConnectionDiagnoser
from bundlemcp.domain.servers.connection_state import ConnectionState
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.observed_response import ObservedResponse
from bundlemcp.domain.servers.probe_failure import ProbeFailure
from bundlemcp.domain.servers.response_log import ResponseLog
from bundlemcp.domain.upstream_oauth.upstream_challenge import UpstreamChallenge
from bundlemcp.infrastructure.egress.egress_policy import EgressDenied, HostUnresolvable
from bundlemcp.infrastructure.fastmcp.response_observer import ResponseObserver
from bundlemcp.infrastructure.fastmcp.upstream_probe import FastMcpUpstreamProbe


async def _send(status: int, headers: dict[str, str] | None = None) -> ResponseLog:
    log = ResponseLog()

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status, headers=headers or {})

    async with httpx2.AsyncClient(
        transport=httpx2.MockTransport(handler), auth=ResponseObserver(log)
    ) as client:
        async with client.stream("POST", "https://up.example/mcp", json={}) as response:
            assert response.status_code == status
    return log


async def test_an_oauth_challenge_is_recorded_with_its_metadata():
    log = await _send(
        401, {"WWW-Authenticate": 'Bearer resource_metadata="https://up.example/prm"'}
    )
    assert log.saw_unauthorized
    assert log.last is not None and log.last.challenge.names_oauth


async def test_a_step_up_challenge_is_found():
    log = await _send(403, {"WWW-Authenticate": 'Bearer error="insufficient_scope", scope="admin"'})
    assert log.insufficient_scope is not None


async def test_usable_answers_are_not_recorded():
    assert (await _send(200, {"Content-Type": "application/json"})).last is None
    assert (await _send(200, {"Content-Type": "text/event-stream"})).last is None
    assert (await _send(202)).last is None
    web_page = await _send(200, {"Content-Type": "text/html"})
    assert web_page.last is not None and web_page.last.status == 200


class _Refusing:
    """A client factory whose client fails the way the MCP client does on an HTTP refusal."""

    def __init__(self, status: int, header: str | None = None, error: Exception | None = None):
        self.status = status
        self.header = header
        self.error = error or RuntimeError("Server returned an error response")

    def __call__(self, server, extra_headers, *, observer=None, **handlers):
        if observer is not None and self.status:
            observer.record(
                ObservedResponse(status=self.status, challenge=UpstreamChallenge.parse(self.header))
            )
        error = self.error

        class _Client:
            async def __aenter__(self):
                raise error

            async def __aexit__(self, *exc):
                return False

        return _Client()


@pytest.mark.parametrize(
    ("factory", "state"),
    [
        (
            _Refusing(401, 'Bearer resource_metadata="https://up.example/prm"'),
            ConnectionState.OAUTH_REQUIRED,
        ),
        (_Refusing(401), ConnectionState.CREDENTIAL_REQUIRED),
        (_Refusing(405), ConnectionState.NOT_MCP),
        (
            _Refusing(0, error=RuntimeError("no HTTP evidence and no transport cause")),
            ConnectionState.ERROR,
        ),
    ],
)
async def test_ups12_a_failed_probe_is_classified(factory, state):
    probe = FastMcpUpstreamProbe(factory)
    with pytest.raises(ProbeFailure) as excinfo:
        await probe.probe(McpServer(name="s", url="https://up.example/mcp"), {})
    assert excinfo.value.state == state


async def test_ups12_a_connection_failure_is_unreachable():
    cause = httpx2.ConnectError("refused")
    error = RuntimeError("Client failed to connect")
    error.__cause__ = cause
    probe = FastMcpUpstreamProbe(_Refusing(0, error=error))
    with pytest.raises(ProbeFailure) as excinfo:
        await probe.probe(McpServer(name="s", url="https://up.example/mcp"), {})
    assert excinfo.value.state == ConnectionState.UNREACHABLE


@pytest.mark.parametrize(
    ("cause", "state"),
    [
        (EgressDenied("up.example:443", "address in blocked range"), ConnectionState.EGRESS_DENIED),
        (HostUnresolvable("up.example", "DNS resolution failed"), ConnectionState.UNREACHABLE),
    ],
    ids=["denied", "unresolvable"],
)
async def test_sec2_a_denial_at_connect_time_keeps_its_state(cause, state):
    """SEC-2: the MCP client wraps a connect-time egress refusal; the probe still names it."""
    group = ExceptionGroup("connection", [cause])
    error = RuntimeError("Client failed to connect")
    error.__cause__ = group
    probe = FastMcpUpstreamProbe(_Refusing(0, error=error))
    with pytest.raises(ProbeFailure) as excinfo:
        await probe.probe(McpServer(name="s", url="https://up.example/mcp"), {})
    assert excinfo.value.state == state


async def test_ups12_without_an_oauth_provider_a_refusal_stays_as_classified():
    failure = ProbeFailure("x", state=ConnectionState.CREDENTIAL_REQUIRED)
    diagnosis = await ConnectionDiagnoser(None).diagnose("https://up.example/mcp", failure)
    assert diagnosis.state == ConnectionState.CREDENTIAL_REQUIRED
