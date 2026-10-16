from contextlib import AbstractAsyncContextManager
from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.inspection.inspector_client import InspectorClient
from bundlemcp.domain.servers.mcp_server import McpServer


@runtime_checkable
class InspectorConnector(Protocol):
    """Opens an inspector connection to an upstream server, stored or transient.

    The connection goes through the gateway's egress policy and carries the
    server's static headers plus ``headers``. Entering the context connects
    and initialises; a target that gives no MCP answer raises ``ProbeFailure``
    with the classified connection state, never the target's own words.
    """

    def open(
        self, server: McpServer, headers: dict[str, str]
    ) -> AbstractAsyncContextManager[InspectorClient]: ...
