"""Upstream MCP connections: the only place clients to upstreams are built.

Streamable HTTP only. The factory is injectable so hermetic tests can
substitute in-process FastMCP servers.
"""

from collections.abc import Callable
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from bundlemcp.application.settings.settings import Settings
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.response_log import ResponseLog
from bundlemcp.infrastructure.egress.egress_policy import check_url_allowed
from bundlemcp.infrastructure.fastmcp.response_observer import ResponseObserver

# (server, extra_headers, *, observer, **handlers) -> Client. `handlers` carries
# the elicitation_handler / sampling_handler / roots / log_handler used to relay a
# server's requests for client input (PROT-4, PROT-18); it is empty unless the
# downstream client advertised the capability. `observer` receives every HTTP
# response the MCP client could not use (UPS-12). The client negotiates the MCP
# revision per server from `server.protocol_mode` (UPS-10, PROT-21).
ClientFactory = Callable[..., Client]


def default_client_factory(settings: Settings) -> ClientFactory:
    def factory(
        server: McpServer,
        extra_headers: dict[str, str],
        *,
        observer: ResponseLog | None = None,
        **handlers: Any,
    ) -> Client:
        check_url_allowed(server.url, settings)  # SEC-1
        headers = {**server.static_headers, **extra_headers}
        auth = ResponseObserver(observer) if observer is not None else None
        return Client(
            StreamableHttpTransport(server.url, headers=headers, auth=auth),
            mode=server.protocol_mode,
            **handlers,
        )

    return factory
