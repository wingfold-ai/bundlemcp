import uuid
from datetime import datetime, timedelta

from pydantic import BaseModel, Field


class UpstreamOAuthToken(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Identifier of the connection")
    server_id: uuid.UUID = Field(
        description="Upstream server the tokens are for",
    )
    user_id: uuid.UUID | None = Field(
        default=None,
        description="User the connection belongs to. Null marks a shared connection every "
        "caller of the server uses",
    )
    tokens_encrypted: str = Field(
        description="The token set, encrypted at rest. Never returned by the API"
    )
    expires_at: datetime | None = Field(
        default=None,
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

    def is_expired_at(self, now: datetime) -> bool:
        """Whether the access token had run out by ``now``."""
        return self.expires_at is not None and self.expires_at < now

    def is_connected_at(self, now: datetime) -> bool:
        """Whether the stored token set is still believed to work upstream at ``now``."""
        return self.is_valid and not self.is_expired_at(now)

    def expires_within(self, skew: timedelta, now: datetime) -> bool:
        """Whether the access token runs out within ``skew`` of ``now`` (or already has)."""
        return self.expires_at is not None and self.expires_at - skew <= now
