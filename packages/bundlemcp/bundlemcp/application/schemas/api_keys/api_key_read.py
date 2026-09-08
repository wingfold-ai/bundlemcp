import uuid
from datetime import datetime

from pydantic import Field

from bundlemcp.application.schemas.common.entity_read import EntityRead
from bundlemcp.domain.access.api_key_kind import ApiKeyKind


class ApiKeyRead(EntityRead):
    """An API key as listed; the secret itself is never returned."""

    id: uuid.UUID = Field(description="Identifier of the key")
    name: str = Field(description="Human-readable label given at creation")
    key_prefix: str = Field(
        description="Leading characters of the secret, enough to recognise which key this is"
    )
    kind: ApiKeyKind = Field(
        description="'endpoint' for MCP access, 'service' for the management API"
    )
    endpoint_ids: list[str] = Field(
        description="Endpoints this key may call; empty means every endpoint"
    )
    is_active: bool = Field(description="Whether the key is currently accepted")
    last_used_at: datetime | None = Field(
        description="When the key last authenticated a request; null if never used"
    )
    created_at: datetime = Field(description="When the key was created")
