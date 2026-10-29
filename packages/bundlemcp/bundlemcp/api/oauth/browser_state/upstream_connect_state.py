import uuid

from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.api.oauth.browser_state.connect_refusal import ConnectRefusal
from bundlemcp.domain.access.user import User


class UpstreamConnectState(BaseModel):
    """What a connect must remember between sending the user upstream and the callback."""

    model_config = ConfigDict(frozen=True)

    server_id: uuid.UUID = Field(description="Server being connected")
    user_id: uuid.UUID | None = Field(
        description="User whose account is being connected; None for the shared connection"
    )
    code_verifier: str = Field(repr=False, description="PKCE verifier for the token exchange")
    redirect_uri: str = Field(description="Callback URL the exchange must repeat exactly")
    issuer: str | None = Field(
        default=None, description="Issuer the callback's 'iss' must equal, when the server has one"
    )
    iss_required: bool = Field(
        default=False, description="Whether a callback without 'iss' is refused"
    )

    def refusal_for(self, user: User | None) -> ConnectRefusal | None:
        """Why ``user``'s browser session may not finish this connect; None when it may.

        A per-user connect is finished only by the user it was started for, and
        the shared connection only by an admin, so a link to the upstream's
        authorize page cannot be handed to someone else to complete.
        """
        if user is None:
            return ConnectRefusal.NO_SESSION
        if self.user_id is None:
            return None if user.is_admin else ConnectRefusal.NOT_ADMIN
        return None if user.id == self.user_id else ConnectRefusal.OTHER_USER
