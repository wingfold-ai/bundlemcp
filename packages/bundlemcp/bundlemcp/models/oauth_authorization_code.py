import uuid
from datetime import datetime

from sqlalchemy import Column, ForeignKey
from sqlmodel import Field, SQLModel

from bundlemcp.models.base import _ts


class OAuthAuthorizationCode(SQLModel, table=True):
    __tablename__ = "oauth_authorization_codes"

    code_hash: str = Field(  # OAS-8
        primary_key=True, description="Hash of the code; the code itself is never stored"
    )
    client_id: str = Field(
        sa_column=Column(ForeignKey("oauth_clients.client_id", ondelete="CASCADE")),
        description="Client the code was issued to",
    )
    user_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("users.id", ondelete="CASCADE")),
        description="User who authorized it",
    )
    endpoint_id: uuid.UUID = Field(  # OAS-10
        sa_column=Column(ForeignKey("endpoints.id", ondelete="CASCADE")),
        description="Endpoint the resulting token will be valid for",
    )
    redirect_uri: str = Field(
        description="Redirect URI used, which the token exchange must repeat exactly"
    )
    scope: str = Field(default="mcp", description="Scopes the code will grant")
    code_challenge: str = Field(description="PKCE challenge the exchange must satisfy")
    code_challenge_method: str = Field(
        default="S256", description="How the challenge was derived; only S256 is accepted"
    )
    expires_at: datetime = Field(sa_column=_ts(), description="When the code expires")
    used: bool = Field(  # OAS-3
        default=False,
        description="Whether the code has been redeemed. A code works exactly once",
    )
