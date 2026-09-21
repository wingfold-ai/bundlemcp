from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.servers.mcp_server import McpServer


class ListedTool(BaseModel):
    """A tool as an endpoint lists it, whoever answers a call to it.

    Listing needs only what a client is shown. What a call does is decided by
    the subclass: an upstream tool is forwarded to its server, a gateway tool
    is answered by the gateway itself. Code that calls tools takes the
    subclass it can handle, never this base.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    presented_name: str = Field(
        description="Name the client sees, either an override or 'server__tool'"
    )
    server: McpServer = Field(description="Member server the tool belongs to")
    title: str | None = Field(description="Display title after any bundle-level override")
    description: str | None = Field(description="Description after any bundle-level override")
    input_schema: dict[str, Any] = Field(description="JSON Schema advertised for the arguments")
    annotations: dict[str, Any] | None = Field(
        description="MCP tool annotations (read-only, destructive and similar hints)"
    )
