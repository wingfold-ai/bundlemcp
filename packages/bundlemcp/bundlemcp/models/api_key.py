import uuid
from datetime import datetime

from sqlalchemy import JSON, Column
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
    kind: str = Field(  # KEY-2
        default=ApiKeyKind.ENDPOINT,
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
