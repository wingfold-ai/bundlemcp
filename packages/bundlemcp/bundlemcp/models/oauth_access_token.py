import uuid
from datetime import datetime

from sqlalchemy import Column, ForeignKey
from sqlmodel import Field, SQLModel

from bundlemcp.models.base import _ts, utcnow


class OAuthAccessToken(SQLModel, table=True):
    __tablename__ = "oauth_access_tokens"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    access_token_hash: str = Field(unique=True, index=True)
    refresh_token_hash: str | None = Field(default=None, unique=True, index=True)
    client_id: str = Field(
        sa_column=Column(ForeignKey("oauth_clients.client_id", ondelete="CASCADE"))
    )
    user_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    )
    endpoint_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("endpoints.id", ondelete="CASCADE"))
    )  # audience (OAS-10)
    scope: str = Field(default="mcp")
    expires_at: datetime = Field(sa_column=_ts())
    refresh_expires_at: datetime | None = Field(default=None, sa_column=_ts())
    revoked: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts())
