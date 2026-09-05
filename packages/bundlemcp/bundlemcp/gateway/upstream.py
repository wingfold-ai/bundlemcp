"""Upstream MCP connections: the only place clients to upstreams are built.

Streamable HTTP only. The factory is injectable so hermetic tests can
substitute in-process FastMCP servers.
"""

from collections.abc import Callable
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from bundlemcp.gateway.egress import check_url_allowed
from bundlemcp.models import McpServer
from bundlemcp.settings import Settings

# (server, extra_headers, **handlers) -> Client. `handlers` carries the
# elicitation_handler / sampling_handler / roots / log_handler used to relay a
# server's requests for client input (PROT-4, PROT-18); it is empty unless the
# downstream client advertised the capability. The client negotiates the MCP
# revision per server from `server.protocol_mode` (SRV-10, PROT-21).
ClientFactory = Callable[..., Client]


def default_client_factory(settings: Settings) -> ClientFactory:
    def factory(server: McpServer, extra_headers: dict[str, str], **handlers: Any) -> Client:
        check_url_allowed(server.url, settings)  # SEC-1
        headers = {**server.static_headers, **extra_headers}
        return Client(
            StreamableHttpTransport(server.url, headers=headers),
            mode=server.protocol_mode,
            **handlers,
        )

    return factory
