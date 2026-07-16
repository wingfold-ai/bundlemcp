import uuid
from datetime import datetime

from sqlalchemy import Column, ForeignKey, UniqueConstraint
from sqlmodel import Field, SQLModel

from bundlemcp.models.base import _ts


class UpstreamOAuthToken(SQLModel, table=True):
    __tablename__ = "upstream_oauth_tokens"
    __table_args__ = (
        UniqueConstraint("server_id", "user_id", name="uq_upstream_tokens_server_user"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    server_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("mcp_servers.id", ondelete="CASCADE"), index=True)
    )
    user_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
    )  # NULL = shared/service connection (UPO-2)
    tokens_encrypted: str  # DOM-3
    expires_at: datetime | None = Field(default=None, sa_column=_ts())
    is_valid: bool = Field(default=True)  # UPO-4
    account_hint: str | None = None  # UPO-5 (e.g. masked account name)
