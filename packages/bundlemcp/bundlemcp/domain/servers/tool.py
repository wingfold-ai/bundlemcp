import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


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
    schema_hash: str = Field(
        description="Hash of the definition, so an unchanged tool costs no write on re-probe"
    )
    stale_since: datetime | None = Field(
        default=None,
        description="When a successful discovery of the server first stopped listing the tool; "
        "None while the server lists it. A stale tool is not served but keeps its curation, "
        "and is served again if the server lists it again",
    )

    @property
    def is_stale(self) -> bool:
        """The latest successful discovery of the server did not list this tool."""
        return self.stale_since is not None
