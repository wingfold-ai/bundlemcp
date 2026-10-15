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
from bundlemcp.infrastructure.fastmcp.guarded_mcp_http_client import guarded_mcp_http_client
from bundlemcp.infrastructure.fastmcp.response_observer import ResponseObserver

# (server, extra_headers, *, observer, **handlers) -> Client. `handlers` carries
# the elicitation_handler / sampling_handler / roots / log_handler used to relay a
# server's requests for client input; it is empty unless the
# downstream client advertised the capability. `observer` receives every HTTP
# response the MCP client could not use. The client negotiates the MCP
# revision per server from `server.protocol_mode`.
ClientFactory = Callable[..., Client]


def default_client_factory(settings: Settings, response_cap: Callable[[], int]) -> ClientFactory:
    """Clients over the guarded HTTP stack, each upstream message capped at ``response_cap()``."""

    def factory(
        server: McpServer,
        extra_headers: dict[str, str],
        *,
        observer: ResponseLog | None = None,
        **handlers: Any,
    ) -> Client:
        check_url_allowed(server.url, settings)  # early, clear refusal; enforced at connect
        headers = {**server.static_headers, **extra_headers}
        auth = ResponseObserver(observer) if observer is not None else None
        return Client(
            StreamableHttpTransport(
                server.url,
                headers=headers,
                auth=auth,
                httpx_client_factory=guarded_mcp_http_client(
                    settings, response_cap=response_cap, log=observer
                ),
            ),
            mode=server.protocol_mode,
            **handlers,
        )

    return factory
