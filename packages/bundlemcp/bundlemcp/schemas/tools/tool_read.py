import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from bundlemcp.schemas.common.entity_read import EntityRead


class ToolRead(EntityRead):
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
    last_seen_at: datetime = Field(
        description="When the tool was last reported by its server. A stale value means the "
        "tool has disappeared upstream and is no longer served"
    )
