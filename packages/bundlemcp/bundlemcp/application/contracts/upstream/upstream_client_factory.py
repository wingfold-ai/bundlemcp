from typing import Any, Protocol, runtime_checkable

from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.response_log import ResponseLog


@runtime_checkable
class UpstreamClientFactory(Protocol):
    """Builds the client one connection to an upstream server speaks through.

    ``handlers`` carries the callbacks that relay a server's requests for client
    input (elicitation, sampling, roots, logging); it is empty unless the
    downstream client advertised the capability. ``observer``, when given,
    receives every HTTP response the client could not use, so the caller can
    tell a refused credential from an unreachable host. The returned object is
    the protocol SDK's client; the MCP edge and the probe adapter know its shape.
    """

    def __call__(
        self,
        server: McpServer,
        extra_headers: dict[str, str],
        *,
        observer: ResponseLog | None = None,
        **handlers: Any,
    ) -> Any: ...
