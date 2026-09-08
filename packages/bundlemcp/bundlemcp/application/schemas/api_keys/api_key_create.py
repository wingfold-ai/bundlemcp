import uuid

from pydantic import BaseModel, Field

from bundlemcp.domain.access.api_key_kind import ApiKeyKind


class ApiKeyCreate(BaseModel):
    """Body for creating an API key."""

    name: str = Field(description="Human-readable label for the key, shown in listings")
    kind: ApiKeyKind = Field(
        default=ApiKeyKind.ENDPOINT,
        description="'endpoint' keys call MCP endpoints; 'service' keys call the management API",
    )
    endpoint_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="Endpoints an endpoint-kind key may call; empty means every endpoint",
    )
