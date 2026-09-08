from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from bundlemcp.domain.servers.mcp_server import McpServer
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


@runtime_checkable
class UpstreamProbe(Protocol):
    """Opens one connection to an upstream server and reports what it offers."""

    async def probe(self, server: McpServer) -> ProbeResult:
        """List the server's tools and capabilities; raises when it cannot be reached."""
        ...
