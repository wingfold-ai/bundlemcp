import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.tool import Tool


class ToolRead(BaseModel):
    """A tool definition as cached from its upstream server."""

    id: uuid.UUID = Field(description="Identifier of the cached tool")
    server_id: uuid.UUID = Field(description="Server that provides the tool")
    name: str = Field(description="Tool name as the upstream server reports it")
    title: str | None = Field(description="Display title the upstream server reports")
    description: str | None = Field(description="Description the upstream server reports")
    input_schema: dict[str, Any] = Field(description="JSON Schema for the tool's arguments")
    annotations: dict[str, Any] | None = Field(
        description="MCP tool annotations such as read-only and destructive hints"
    )
    stale: bool = Field(
        description="True when the latest successful discovery of the server no longer listed "
        "the tool. A stale tool is not served by any endpoint but keeps its curation; it is "
        "served again if the server lists it again, and a refresh with prune deletes it"
    )
    last_seen_at: datetime | None = Field(
        description="When a successful discovery last listed the tool; for a stale tool, when "
        "a discovery first found it missing. Absent only for a server with no recorded "
        "successful discovery"
    )

    @classmethod
    def of(cls, tool: Tool, server: McpServer) -> ToolRead:
        return cls(
            id=tool.id,
            server_id=tool.server_id,
            name=tool.name,
            title=tool.title,
            description=tool.description,
            input_schema=tool.input_schema,
            annotations=tool.annotations,
            stale=tool.is_stale,
            last_seen_at=tool.stale_since if tool.is_stale else server.last_discovered_at,
        )
