from datetime import datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from bundlemcp.models.base import _ts, utcnow


class OAuthClient(SQLModel, table=True):
    __tablename__ = "oauth_clients"

    client_id: str = Field(primary_key=True, description="Identifier issued to the client")
    client_secret_hash: str | None = Field(
        default=None,
        description="Hash of the client secret. Null marks a public client, which proves "
        "itself with PKCE instead",
    )
    client_name: str | None = Field(
        default=None, description="Name shown to the user on the consent screen"
    )
    redirect_uris: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="URIs the authorization response may be sent to",
    )
    grant_types: list[str] = Field(
        default_factory=lambda: ["authorization_code", "refresh_token"],
        sa_column=Column(JSON),
        description="Grant types this client registered for",
    )
    token_endpoint_auth_method: str = Field(
        default="none", description="How the client authenticates at the token endpoint"
    )
    scope: str = Field(default="mcp", description="Space-separated scopes the client may request")
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=_ts(), description="When the client registered"
    )
    last_used_at: datetime | None = Field(  # SEC-8
        default=None,
        sa_column=_ts(),
        description="When the client last obtained a token. Clients that never used one are "
        "purged, so abandoned registrations do not accumulate",
    )
