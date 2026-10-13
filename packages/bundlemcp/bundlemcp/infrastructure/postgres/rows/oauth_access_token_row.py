"""The ``oauth_access_tokens`` table, as SQLAlchemy sees it."""

import uuid
from datetime import datetime

from sqlalchemy import Column, ForeignKey
from sqlmodel import Field, SQLModel

from bundlemcp.domain.shared.clock import utcnow
from bundlemcp.infrastructure.postgres.utc_datetime import timestamp_column


class OAuthAccessTokenRow(SQLModel, table=True):
    __tablename__ = "oauth_access_tokens"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, primary_key=True, description="Identifier of the token pair"
    )
    access_token_hash: str = Field(
        unique=True, index=True, description="Hash of the access token; the token is not stored"
    )
    refresh_token_hash: str | None = Field(
        default=None,
        unique=True,
        index=True,
        description="Hash of the refresh token, when one was issued",
    )
    client_id: str = Field(
        sa_column=Column(ForeignKey("oauth_clients.client_id", ondelete="CASCADE")),
        description="Client the token was issued to",
    )
    user_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"), index=True),
        description="User who authorized it",
    )
    endpoint_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("endpoints.id", ondelete="CASCADE")),
        description="Endpoint the token is valid for. A token presented to any other endpoint "
        "is rejected as the wrong audience",
    )
    family_id: uuid.UUID = Field(  # RFC 9700 section 4.14.2
        default_factory=uuid.uuid4,
        index=True,
        description="Groups every pair descended from one authorization grant through refresh "
        "rotation. A replayed refresh token revokes the whole family",
    )
    scope: str = Field(default="mcp", description="Scopes granted")
    expires_at: datetime = Field(
        sa_column=timestamp_column(),
        description="When the access token expires",
    )
    refresh_expires_at: datetime | None = Field(
        default=None,
        sa_column=timestamp_column(),
        description="When the refresh token expires, if there is one",
    )
    revoked: bool = Field(
        default=False, description="Whether the pair has been revoked before expiry"
    )
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=timestamp_column(), description="When the pair was issued"
    )
