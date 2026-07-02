"""Upstream MCP connections (spec 10): the only place clients to upstreams are built.

Streamable HTTP only (SRV-1/ADR-0005). The factory is injectable so hermetic
tests can substitute in-process FastMCP servers.
"""

from collections.abc import Callable

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from bundlemcp.gateway.egress import check_url_allowed
from bundlemcp.models import McpServer
from bundlemcp.settings import Settings

# extra per-request headers (forwarded identity, FWD-1/FWD-3) -> Client
ClientFactory = Callable[[McpServer, dict[str, str]], Client]


def default_client_factory(settings: Settings) -> ClientFactory:
    def factory(server: McpServer, extra_headers: dict[str, str]) -> Client:
        check_url_allowed(server.url, settings)  # SEC-1
        headers = {**server.static_headers, **extra_headers}
        return Client(StreamableHttpTransport(server.url, headers=headers))

    return factory
