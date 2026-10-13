"""The ``upstream_oauth_tokens`` table, as SQLAlchemy sees it."""

import uuid
from datetime import datetime

from sqlalchemy import Column, ForeignKey, UniqueConstraint
from sqlmodel import Field, SQLModel

from bundlemcp.infrastructure.postgres.utc_datetime import timestamp_column


class UpstreamOAuthTokenRow(SQLModel, table=True):
    __tablename__ = "upstream_oauth_tokens"
    __table_args__ = (
        UniqueConstraint("server_id", "user_id", name="uq_upstream_tokens_server_user"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, primary_key=True, description="Identifier of the connection"
    )
    server_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("mcp_servers.id", ondelete="CASCADE"), index=True),
        description="Upstream server the tokens are for",
    )
    user_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        description="User the connection belongs to. Null marks a shared connection every "
        "caller of the server uses",
    )
    tokens_encrypted: str = Field(
        description="The token set, encrypted at rest. Never returned by the API"
    )
    expires_at: datetime | None = Field(
        default=None,
        sa_column=timestamp_column(),
        description="When the access token expires, used to refresh before it does",
    )
    is_valid: bool = Field(
        default=True,
        description="Whether the connection still works. Cleared when the upstream rejects a "
        "refresh, so the user is prompted to reconnect",
    )
    account_hint: str | None = Field(
        default=None,
        description="Masked account or email identifying which upstream account this is",
    )
