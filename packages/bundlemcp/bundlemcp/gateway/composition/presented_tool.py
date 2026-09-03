from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.models import McpServer, Tool

PREFIX_SEP = "__"  # BND-2: separates the bundle prefix from the upstream tool name


class PresentedTool(BaseModel):
    """One tool as an endpoint shows it, after curation and profile transforms."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    presented_name: str = Field(
        description="Name the client sees, either an override or 'server__tool'"
    )
    server: McpServer = Field(description="Upstream server the call is routed to")
    tool: Tool = Field(description="Cached upstream definition this was derived from")
    title: str | None = Field(description="Display title after any bundle-level override")
    description: str | None = Field(description="Description after any bundle-level override")
    input_schema: dict[str, Any] = Field(description="JSON Schema advertised for the arguments")
    annotations: dict[str, Any] | None = Field(
        description="MCP tool annotations (read-only, destructive and similar hints)"
    )
