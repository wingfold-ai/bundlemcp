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
        default=None,
        description="Resource identifier the token is valid for: the endpoint's URL, or the "
        "upstream server's URL for a delegated token",
    )
    email: str | None = Field(default=None, description="Email of the user, when known")
    oidc_iss: str | None = Field(  # OAS-5
        default=None,
        description="Issuer of the identity provider that authenticated the user. Present for "
        "a user's token and for a token delegated on a user's behalf; absent for an API key",
    )
    oidc_sub: str | None = Field(  # OAS-5
        default=None,
        description="The user's subject at that identity provider: stable across logins and "
        "across a rebuild of the gateway's database, unlike 'sub'. Present and absent as "
        "'oidc_iss' is",
    )
    token_use: str | None = Field(
        default=None,
        description="'api_key' when the presented value was a gateway API key, 'delegated' "
        "when it was a token the gateway issued for one upstream server on a caller's behalf",
    )
    act: dict[str, str] | None = Field(
        default=None,
        description="For a delegated token, the actor it was issued through: {'sub': "
        "'endpoint:<name>'}",
    )
