"""The HTTP client the MCP transport uses toward upstreams."""

from collections.abc import Callable

import httpx2
from mcp.shared._httpx_utils import (
    MCP_DEFAULT_SSE_READ_TIMEOUT,
    MCP_DEFAULT_TIMEOUT,
    McpHttpClientFactory,
)

from bundlemcp.application.settings.settings import Settings
from bundlemcp.domain.servers.response_log import ResponseLog
from bundlemcp.infrastructure.egress.guarded_backend import guard_pool
from bundlemcp.infrastructure.fastmcp.response_cap import CappedResponses
from bundlemcp.infrastructure.fastmcp.transport_failures import RecordedTransportFailures


def guarded_mcp_http_client(
    settings: Settings,
    *,
    response_cap: Callable[[], int] | None = None,
    log: ResponseLog | None = None,
    wrap: Callable[[httpx2.AsyncBaseTransport], httpx2.AsyncBaseTransport] | None = None,
) -> McpHttpClientFactory:
    """The MCP SDK's client factory, with every connection passing the egress policy.

    With a ``response_cap``, each upstream message larger than it is abandoned
    and the overflow recorded on ``log``. With a ``log``, a connection or a
    stream that fails below HTTP is noted on it too.

    Keeps the SDK's defaults: its timeouts, and redirects left to the MCP
    transport, which follows them only within the upstream's origin. FastMCP
    asks a custom factory for ``follow_redirects=True``; that is ignored, since
    the client would then follow cross-origin redirects the SDK's own client
    does not. Each followed hop opens its connection through the same guard.
    ``trust_env`` is off so a proxy from the environment cannot route around
    the policy. ``wrap``, when given, is the outermost layer around the
    transport.
    """

    def factory(
        headers: dict[str, str] | None = None,
        timeout: httpx2.Timeout | None = None,
        auth: httpx2.Auth | None = None,
        follow_redirects: bool = False,
    ) -> httpx2.AsyncClient:
        pool = httpx2.AsyncHTTPTransport(trust_env=False)
        guard_pool(pool._pool, settings)
        transport: httpx2.AsyncBaseTransport = (
            pool if log is None else RecordedTransportFailures(pool, log)
        )
        if response_cap is not None:
            transport = CappedResponses(transport, response_cap, log)
        if wrap is not None:
            transport = wrap(transport)
        return httpx2.AsyncClient(
            headers=headers,
            timeout=timeout
            or httpx2.Timeout(MCP_DEFAULT_TIMEOUT, read=MCP_DEFAULT_SSE_READ_TIMEOUT),
            auth=auth,
            transport=transport,
            trust_env=False,
        )

    return factory
