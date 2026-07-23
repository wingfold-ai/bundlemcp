from datetime import datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from bundlemcp.models.base import _ts, utcnow


class OAuthClient(SQLModel, table=True):
    __tablename__ = "oauth_clients"

    client_id: str = Field(primary_key=True)
    client_secret_hash: str | None = None  # None => public client (PKCE)
    client_name: str | None = None
    redirect_uris: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    grant_types: list[str] = Field(
        default_factory=lambda: ["authorization_code", "refresh_token"],
        sa_column=Column(JSON),
    )
    token_endpoint_auth_method: str = Field(default="none")
    scope: str = Field(default="mcp")
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts())
    last_used_at: datetime | None = Field(default=None, sa_column=_ts())  # SEC-8 purge
