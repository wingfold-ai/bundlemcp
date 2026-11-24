import uuid
from typing import Self

from pydantic import BaseModel, Field, model_validator

from bundlemcp.domain.access.api_key_kind import ApiKeyKind
from bundlemcp.domain.access.api_key_scope import ApiKeyScope


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
    scopes: list[ApiKeyScope] = Field(
        default=[],
        description="Limits a service key to these scopes: introspect, read, bundles:write, "
        "endpoints:write, upstreams:write, keys:manage, mcp. Empty gives a service key every "
        "right; an endpoint key takes none",
    )

    @model_validator(mode="after")
    def _scopes_are_for_service_keys(self) -> Self:
        if self.scopes and self.kind is not ApiKeyKind.SERVICE:
            raise ValueError("only a service key takes scopes")
        self.scopes = sorted(set(self.scopes))
        return self
