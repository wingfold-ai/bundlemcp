import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, String
from sqlmodel import Field, SQLModel

from bundlemcp.models.api_key_kind import ApiKeyKind
from bundlemcp.models.base import _ts, utcnow


class ApiKey(SQLModel, table=True):
    __tablename__ = "api_keys"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, primary_key=True, description="Identifier of the key"
    )
    name: str = Field(description="Human-readable label, shown in listings")
    key_hash: str = Field(  # KEY-1
        unique=True,
        index=True,
        description="Hash of the secret. The secret itself is never stored",
    )
    key_prefix: str = Field(
        description="Leading characters of the secret, enough to recognise which key this is"
    )
    kind: ApiKeyKind = Field(  # KEY-2
        default=ApiKeyKind.ENDPOINT,
        sa_type=String,
        description="'endpoint' keys call MCP endpoints; 'service' keys call the management API",
    )
    endpoint_ids: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="Endpoints this key may call; empty means every endpoint",
    )
    is_active: bool = Field(default=True, description="Whether the key is currently accepted")
    last_used_at: datetime | None = Field(
        default=None,
        sa_column=_ts(),
        description="When the key last authenticated a request; null if never used",
    )
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=_ts(), description="When the record was created"
    )

    @property
    def is_service_key(self) -> bool:
        return self.kind == ApiKeyKind.SERVICE

    def reaches(self, endpoint_id: uuid.UUID) -> bool:
        """Whether the key may call this endpoint; an unscoped key reaches every one."""
        # KEY-2
        if self.kind == ApiKeyKind.ENDPOINT and self.endpoint_ids:
            return str(endpoint_id) in self.endpoint_ids
        return True

    def used_within(self, seconds: int, now: datetime) -> bool:
        """Whether the last recorded use is recent enough to skip another write."""
        if self.last_used_at is None:
            return False
        return (now - self.last_used_at).total_seconds() <= seconds
