"""The ``api_keys`` table, as SQLAlchemy sees it."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, String
from sqlmodel import Field, SQLModel

from bundlemcp.domain.access.api_key_kind import ApiKeyKind
from bundlemcp.domain.shared.clock import utcnow
from bundlemcp.infrastructure.postgres.utc_datetime import timestamp_column


class ApiKeyRow(SQLModel, table=True):
    __tablename__ = "api_keys"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, primary_key=True, description="Identifier of the key"
    )
    name: str = Field(description="Human-readable label, shown in listings")
    key_hash: str = Field(
        unique=True,
        index=True,
        description="Hash of the secret. The secret itself is never stored",
    )
    key_prefix: str = Field(
        description="Leading characters of the secret, enough to recognise which key this is"
    )
    kind: ApiKeyKind = Field(
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
        sa_column=timestamp_column(),
        description="When the key last authenticated a request; null if never used",
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=timestamp_column(),
        description="When the record was created",
    )
