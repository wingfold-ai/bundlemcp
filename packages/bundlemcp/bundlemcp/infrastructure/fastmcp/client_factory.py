"""Upstream MCP connections: the only place clients to upstreams are built.

Streamable HTTP only. The factory is injectable so hermetic tests can
substitute in-process FastMCP servers.
"""

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from bundlemcp.application.settings.settings import Settings
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.response_log import ResponseLog
from bundlemcp.infrastructure.egress.egress_policy import check_url_allowed
from bundlemcp.infrastructure.fastmcp.connect_mode import connect_mode
from bundlemcp.infrastructure.fastmcp.guarded_mcp_http_client import guarded_mcp_http_client
from bundlemcp.infrastructure.fastmcp.lease_headers import LeaseHeaders
from bundlemcp.infrastructure.fastmcp.lease_slot import (
    MCP_PROTOCOL_VERSION,
    MCP_SESSION_ID,
    LeaseSlot,
    SlotResponseLog,
)
from bundlemcp.infrastructure.fastmcp.response_observer import ResponseObserver
from bundlemcp.infrastructure.fastmcp.session_end_guard import SessionEndGuard

# (server, extra_headers, *, observer, **handlers) -> Client. `handlers` carries
# the elicitation_handler / sampling_handler / roots / log_handler used to relay a
# server's requests for client input; it is empty unless the
# downstream client advertised the capability. `observer` receives every HTTP
# response the MCP client could not use. The client negotiates the MCP
# revision per server from `server.protocol_mode`, through `connect_mode`.
ClientFactory = Callable[..., Client]


@runtime_checkable
class LeaseAwareClientFactory(Protocol):
    """A client factory that can build a transport for a pooled upstream session.

    A pooled transport reads each request's headers and response log from a
    ``LeaseSlot`` rather than having them fixed at construction, and never
    ends its upstream session when it closes; ``end_session`` does that.
    """

    def for_lease(
        self, server: McpServer, slot: LeaseSlot, *, auto_initialize: bool, **handlers: Any
    ) -> Client: ...

    async def end_session(
        self,
        server: McpServer,
        session_id: str,
        protocol_version: str | None,
        headers: dict[str, str],
    ) -> None: ...


class GuardedClientFactory:
    """Clients over the guarded HTTP stack, each upstream message capped at ``response_cap()``."""

    def __init__(self, settings: Settings, response_cap: Callable[[], int]) -> None:
        self._settings = settings
        self._response_cap = response_cap

    def __call__(
        self,
        server: McpServer,
        extra_headers: dict[str, str],
        *,
        observer: ResponseLog | None = None,
        **handlers: Any,
    ) -> Client:
        check_url_allowed(server.url, self._settings)  # early, clear refusal; enforced at connect
        headers = {**server.static_headers, **extra_headers}
        auth = ResponseObserver(observer) if observer is not None else None
        return Client(
            StreamableHttpTransport(
                server.url,
                headers=headers,
                auth=auth,
                httpx_client_factory=guarded_mcp_http_client(
                    self._settings, response_cap=self._response_cap, log=observer
                ),
            ),
            mode=connect_mode(server.protocol_mode),
            **handlers,
        )

    def for_lease(
        self, server: McpServer, slot: LeaseSlot, *, auto_initialize: bool, **handlers: Any
    ) -> Client:
        check_url_allowed(server.url, self._settings)
        log = SlotResponseLog(slot)

        return Client(
            StreamableHttpTransport(
                server.url,
                headers=dict(server.static_headers),
                auth=LeaseHeaders(slot, ResponseObserver(log)),
                httpx_client_factory=guarded_mcp_http_client(
                    self._settings, response_cap=self._response_cap, log=log, wrap=SessionEndGuard
                ),
            ),
            mode=connect_mode(server.protocol_mode),
            auto_initialize=auto_initialize,
            **handlers,
        )

    async def end_session(
        self,
        server: McpServer,
        session_id: str,
        protocol_version: str | None,
        headers: dict[str, str],
    ) -> None:
        """Ask the upstream to end one session; an upstream that refuses is left to expire it."""
        check_url_allowed(server.url, self._settings)
        session = {MCP_SESSION_ID: session_id}
        if protocol_version is not None:
            session[MCP_PROTOCOL_VERSION] = protocol_version
        client = guarded_mcp_http_client(self._settings)(
            headers={**server.static_headers, **headers, **session}
        )
        async with client:
            await client.delete(server.url)


def default_client_factory(
    settings: Settings, response_cap: Callable[[], int]
) -> GuardedClientFactory:
    return GuardedClientFactory(settings, response_cap)
