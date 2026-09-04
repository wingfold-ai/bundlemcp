from pydantic import BaseModel, ConfigDict, Field


class AuthorizeStart(BaseModel):
    """Where to send the user, and the secret to keep until they come back."""

    model_config = ConfigDict(frozen=True)

    url: str = Field(description="The upstream authorization URL to redirect the browser to")
    code_verifier: str = Field(repr=False, description="PKCE verifier for the token exchange")
