from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.probed_server_info import ProbedServerInfo
from bundlemcp.domain.servers.probed_tool import ProbedTool


class ProbeResult(BaseModel):
    """What one connection to an upstream server revealed."""

    tools: list[ProbedTool] = Field(description="The tools the server listed")
    capabilities: dict[str, Any] | None = Field(
        description="The capabilities the server advertised, as it serialises them; None when "
        "the connection reported none"
    )
    protocol_version: str | None = Field(
        description="The MCP revision negotiated with the server; None when unknown"
    )
    server_info: ProbedServerInfo | None = Field(
        default=None, description="How the server describes itself, when it said"
    )


@runtime_checkable
class UpstreamProbe(Protocol):
    """Opens one connection to an upstream server and reports what it offers."""

    async def probe(self, server: McpServer, headers: dict[str, str]) -> ProbeResult:
        """List the server's tools and capabilities.

        ``headers`` are sent on top of the server's static headers, which is how
        a probe carries the upstream credential a server requires. Raises
        ``ProbeFailure`` with the classified connection state when the server
        gives no MCP answer.
        """
        ...
