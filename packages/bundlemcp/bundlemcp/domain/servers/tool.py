import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from bundlemcp.domain.shared.clock import utcnow


class Tool(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Identifier of the cached tool")
    server_id: uuid.UUID = Field(
        description="Server that provides the tool",
    )
    name: str = Field(description="Tool name as the upstream server reports it")
    title: str | None = Field(default=None, description="Display title the upstream server reports")
    description: str | None = Field(
        default=None, description="Description the upstream server reports"
    )
    input_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema for the tool's arguments",
    )
    annotations: dict[str, Any] | None = Field(
        default=None,
        description="MCP tool annotations such as read-only and destructive hints",
    )
    schema_hash: str = Field(  # DISC-2
        description="Hash of the definition, so an unchanged tool costs no write on re-probe"
    )
    last_seen_at: datetime = Field(  # DISC-3
        default_factory=utcnow,
        description="When the tool was last reported. A stale value means it has disappeared "
        "upstream and is no longer served, though its curation is kept",
    )
