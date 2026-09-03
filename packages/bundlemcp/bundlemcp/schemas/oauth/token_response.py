from typing import Literal

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    """A freshly issued access and refresh token pair (RFC 6749 section 5.1)."""

    access_token: str = Field(description="Bearer token for the endpoint the grant was bound to")
    token_type: Literal["Bearer"] = Field(default="Bearer", description="Always Bearer")
    expires_in: int = Field(description="Seconds until the access token expires")
    refresh_token: str = Field(description="Token to obtain the next pair; single use")
    scope: str = Field(description="Space-separated scopes granted")
