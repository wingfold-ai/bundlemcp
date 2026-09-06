from pydantic import BaseModel, ConfigDict, Field


class TokenRequest(BaseModel):
    """The grant-specific parameters of a token request, as the client sent them."""

    model_config = ConfigDict(frozen=True)

    grant_type: str = Field(description="Which grant the client is exercising")
    code: str | None = Field(
        default=None, repr=False, description="Authorization code being redeemed"
    )
    redirect_uri: str | None = Field(
        default=None, description="Redirect URI used in the authorization request"
    )
    code_verifier: str | None = Field(
        default=None, repr=False, description="PKCE verifier for the code"
    )
    refresh_token: str | None = Field(
        default=None, repr=False, description="Refresh token being rotated"
    )
