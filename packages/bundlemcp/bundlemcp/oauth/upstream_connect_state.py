import uuid

from pydantic import BaseModel, ConfigDict, Field


class UpstreamConnectState(BaseModel):
    """What a connect must remember between sending the user upstream and the callback."""

    model_config = ConfigDict(frozen=True)

    server_id: uuid.UUID = Field(description="Server being connected")
    user_id: uuid.UUID | None = Field(
        description="User whose account is being connected; None for the shared connection"
    )
    code_verifier: str = Field(repr=False, description="PKCE verifier for the token exchange")
    redirect_uri: str = Field(description="Callback URL the exchange must repeat exactly")
