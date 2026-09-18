import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from bundlemcp.domain.shared.clock import utcnow


class OAuthAccessToken(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Identifier of the token pair")
    access_token_hash: str = Field(description="Hash of the access token; the token is not stored")
    refresh_token_hash: str | None = Field(
        default=None,
        description="Hash of the refresh token, when one was issued",
    )
    client_id: str = Field(
        description="Client the token was issued to",
    )
    user_id: uuid.UUID = Field(
        description="User who authorized it",
    )
    endpoint_id: uuid.UUID = Field(  # OAS-10
        description="Endpoint the token is valid for. A token presented to any other endpoint "
        "is rejected as the wrong audience",
    )
    family_id: uuid.UUID = Field(  # OAS-4, RFC 9700 section 4.14.2
        default_factory=uuid.uuid4,
        description="Groups every pair descended from one authorization grant through refresh "
        "rotation. A replayed refresh token revokes the whole family",
    )
    scope: str = Field(default="mcp", description="Scopes granted")
    expires_at: datetime = Field(
        description="When the access token expires",
    )
    refresh_expires_at: datetime | None = Field(
        default=None,
        description="When the refresh token expires, if there is one",
    )
    revoked: bool = Field(
        default=False, description="Whether the pair has been revoked before expiry"
    )
    created_at: datetime = Field(default_factory=utcnow, description="When the pair was issued")

    def is_usable_at(self, now: datetime) -> bool:
        """The access token still authenticates: neither revoked nor past its expiry."""
        return not self.revoked and self.expires_at >= now

    def is_refreshable_at(self, now: datetime) -> bool:
        """The refresh token may still be exchanged for a new pair."""
        return (
            not self.revoked
            and self.refresh_expires_at is not None
            and self.refresh_expires_at >= now
        )
