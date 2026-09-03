from pydantic import BaseModel, Field


class IntrospectionResponse(BaseModel):
    """What a resource server learns about a presented token (RFC 7662)."""

    active: bool = Field(description="Whether the token currently authenticates anyone")
    sub: str | None = Field(
        default=None,
        description="Subject: the user id, or 'api_key:<id>' when the token was a gateway API key",
    )
    client_id: str | None = Field(default=None, description="Client the token was issued to")
    scope: str | None = Field(default=None, description="Scopes granted")
    exp: int | None = Field(default=None, description="Expiry as a Unix timestamp")
    aud: str | None = Field(
        default=None, description="Resource identifier of the endpoint the token is valid for"
    )
    email: str | None = Field(default=None, description="Email of the user, when known")
    token_use: str | None = Field(
        default=None, description="'api_key' when the presented value was a gateway API key"
    )
