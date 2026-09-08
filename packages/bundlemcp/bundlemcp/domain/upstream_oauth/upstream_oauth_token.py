import uuid
from datetime import datetime, timedelta

from pydantic import BaseModel, Field

from bundlemcp.domain.shared.clock import utcnow


class UpstreamOAuthToken(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Identifier of the connection")
    server_id: uuid.UUID = Field(
        description="Upstream server the tokens are for",
    )
    user_id: uuid.UUID | None = Field(  # UPO-2
        default=None,
        description="User the connection belongs to. Null marks a shared connection every "
        "caller of the server uses",
    )
    tokens_encrypted: str = Field(  # DOM-3
        description="The token set, encrypted at rest. Never returned by the API"
    )
    expires_at: datetime | None = Field(
        default=None,
        description="When the access token expires, used to refresh before it does",
    )
    is_valid: bool = Field(  # UPO-4
        default=True,
        description="Whether the connection still works. Cleared when the upstream rejects a "
        "refresh, so the user is prompted to reconnect",
    )
    account_hint: str | None = Field(  # UPO-5
        default=None,
        description="Masked account or email identifying which upstream account this is",
    )

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and self.expires_at < utcnow()

    @property
    def is_connected(self) -> bool:
        """The stored token set is still believed to work upstream."""
        return self.is_valid and not self.is_expired

    def expires_within(self, skew: timedelta) -> bool:
        """Whether the access token runs out inside the given window (or already has)."""
        return self.expires_at is not None and self.expires_at - skew <= utcnow()
