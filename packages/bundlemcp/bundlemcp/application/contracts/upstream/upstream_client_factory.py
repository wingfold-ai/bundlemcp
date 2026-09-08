from typing import Any, Protocol, runtime_checkable

from bundlemcp.domain.servers.mcp_server import McpServer


@runtime_checkable
class UpstreamClientFactory(Protocol):
    """Builds the client one connection to an upstream server speaks through.

    ``handlers`` carries the callbacks that relay a server's requests for client
    input (elicitation, sampling, roots, logging); it is empty unless the
    downstream client advertised the capability. The returned object is the
    protocol SDK's client; the MCP edge and the probe adapter know its shape.
    """

    def __call__(
        self, server: McpServer, extra_headers: dict[str, str], **handlers: Any
    ) -> Any: ...
