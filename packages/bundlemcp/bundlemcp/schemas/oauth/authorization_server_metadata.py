from pydantic import BaseModel, Field


class AuthorizationServerMetadata(BaseModel):
    """This gateway's OAuth authorization server, as clients discover it (RFC 8414)."""

    issuer: str = Field(description="The public base URL of the gateway")
    authorization_endpoint: str = Field(description="Where to send the user to authorize")
    token_endpoint: str = Field(description="Where to exchange codes and refresh tokens")
    registration_endpoint: str = Field(description="Where a client registers itself")
    introspection_endpoint: str = Field(description="Where a resource server checks a token")
    revocation_endpoint: str = Field(description="Where a client revokes a token")
    response_types_supported: list[str] = Field(default=["code"], description="Only code")
    grant_types_supported: list[str] = Field(
        default=["authorization_code", "refresh_token"], description="Supported grants"
    )
    code_challenge_methods_supported: list[str] = Field(
        default=["S256"], description="PKCE methods; plain is not accepted"
    )
    token_endpoint_auth_methods_supported: list[str] = Field(
        default=["none", "client_secret_basic", "client_secret_post"],
        description="How clients may authenticate at the token endpoint",
    )
    scopes_supported: list[str] = Field(default=["mcp"], description="Scopes a client may request")

    @classmethod
    def for_issuer(cls, issuer: str) -> "AuthorizationServerMetadata":
        return cls(
            issuer=issuer,
            authorization_endpoint=f"{issuer}/oauth/authorize",
            token_endpoint=f"{issuer}/oauth/token",
            registration_endpoint=f"{issuer}/oauth/register",
            introspection_endpoint=f"{issuer}/oauth/introspect",
            revocation_endpoint=f"{issuer}/oauth/revoke",
        )
