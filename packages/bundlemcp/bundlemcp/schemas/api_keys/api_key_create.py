import uuid
from typing import Literal

from pydantic import BaseModel, Field


class ApiKeyCreate(BaseModel):
    """Body for creating an API key."""

    name: str = Field(description="Human-readable label for the key, shown in listings")
    kind: Literal["endpoint", "service"] = Field(
        default="endpoint",
        description="'endpoint' keys call MCP endpoints; 'service' keys call the management API",
    )
    endpoint_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="Endpoints an endpoint-kind key may call; empty means every endpoint",
    )
