"""The HTTP client the MCP transport uses toward upstreams."""

import httpx2
from mcp.shared._httpx_utils import (
    MCP_DEFAULT_SSE_READ_TIMEOUT,
    MCP_DEFAULT_TIMEOUT,
    McpHttpClientFactory,
)

from bundlemcp.application.settings.settings import Settings
from bundlemcp.infrastructure.egress.guarded_backend import guard_pool


def guarded_mcp_http_client(settings: Settings) -> McpHttpClientFactory:
    """The MCP SDK's client factory, with every connection passing the egress policy.

    Keeps the SDK's defaults: its timeouts, and redirects left to the MCP
    transport, which follows them only within the upstream's origin. FastMCP
    asks a custom factory for ``follow_redirects=True``; that is ignored, since
    the client would then follow cross-origin redirects the SDK's own client
    does not. Each followed hop opens its connection through the same guard.
    ``trust_env`` is off so a proxy from the environment cannot route around
    the policy.
    """

    def factory(
        headers: dict[str, str] | None = None,
        timeout: httpx2.Timeout | None = None,
        auth: httpx2.Auth | None = None,
        follow_redirects: bool = False,
    ) -> httpx2.AsyncClient:
        transport = httpx2.AsyncHTTPTransport(trust_env=False)
        guard_pool(transport._pool, settings)
        return httpx2.AsyncClient(
            headers=headers,
            timeout=timeout
            or httpx2.Timeout(MCP_DEFAULT_TIMEOUT, read=MCP_DEFAULT_SSE_READ_TIMEOUT),
            auth=auth,
            transport=transport,
            trust_env=False,
        )

    return factory
