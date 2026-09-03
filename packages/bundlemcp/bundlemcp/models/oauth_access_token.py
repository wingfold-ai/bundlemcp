import uuid
from datetime import datetime

from sqlalchemy import Column, ForeignKey
from sqlmodel import Field, SQLModel

from bundlemcp.models.base import _ts, utcnow


class OAuthAccessToken(SQLModel, table=True):
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
    endpoint_id: uuid.UUID = Field(  # OAS-10
        sa_column=Column(ForeignKey("endpoints.id", ondelete="CASCADE")),
        description="Endpoint the token is valid for. A token presented to any other endpoint "
        "is rejected as the wrong audience",
    )
    scope: str = Field(default="mcp", description="Scopes granted")
    expires_at: datetime = Field(sa_column=_ts(), description="When the access token expires")
    refresh_expires_at: datetime | None = Field(
        default=None, sa_column=_ts(), description="When the refresh token expires, if there is one"
    )
    revoked: bool = Field(
        default=False, description="Whether the pair has been revoked before expiry"
    )
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=_ts(), description="When the pair was issued"
    )

    @property
    def is_expired(self) -> bool:
        return self.expires_at < utcnow()

    @property
    def refresh_is_expired(self) -> bool:
        return self.refresh_expires_at is None or self.refresh_expires_at < utcnow()

    @property
    def is_usable(self) -> bool:
        """The access token still authenticates: neither revoked nor past its expiry."""
        return not self.revoked and not self.is_expired

    @property
    def is_refreshable(self) -> bool:
        """The refresh token may still be exchanged for a new pair."""
        return not self.revoked and not self.refresh_is_expired
