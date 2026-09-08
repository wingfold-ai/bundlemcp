from datetime import datetime

from pydantic import BaseModel, Field


class UpstreamConnectionStatus(BaseModel):
    """Whether one upstream OAuth connection currently works, without any token material."""

    connected: bool = Field(
        default=False, description="Whether a valid, unexpired token set is stored"
    )
    valid: bool = Field(
        default=False,
        description="Whether the upstream last accepted the stored tokens; false after a failed "
        "refresh until the account is reconnected",
    )
    expires_at: datetime | None = Field(
        default=None, description="When the current access token expires, if known"
    )
    account_hint: str | None = Field(
        default=None, description="Masked account or email identifying the connected account"
    )
