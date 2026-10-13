from pydantic import BaseModel, Field

from bundlemcp.domain.oauth.code_challenge_method import CodeChallengeMethod
from bundlemcp.domain.oauth.grant_type import GrantType
from bundlemcp.domain.oauth.response_type import ResponseType
from bundlemcp.domain.oauth.token_endpoint_auth_method import TokenEndpointAuthMethod


class AuthorizationServerMetadata(BaseModel):
    """This gateway's OAuth authorization server, as clients discover it (RFC 8414)."""

    issuer: str = Field(description="The public base URL of the gateway")
    authorization_endpoint: str = Field(description="Where to send the user to authorize")
    token_endpoint: str = Field(description="Where to exchange codes and refresh tokens")
    registration_endpoint: str = Field(description="Where a client registers itself")
    introspection_endpoint: str = Field(description="Where a resource server checks a token")
    revocation_endpoint: str = Field(description="Where a client revokes a token")
    response_types_supported: list[ResponseType] = Field(
        default_factory=lambda: list(ResponseType), description="Only code"
    )
    grant_types_supported: list[GrantType] = Field(
        default_factory=lambda: list(GrantType), description="Supported grants"
    )
    code_challenge_methods_supported: list[CodeChallengeMethod] = Field(
        default_factory=lambda: list(CodeChallengeMethod),
        description="PKCE methods; plain is not accepted",
    )
    token_endpoint_auth_methods_supported: list[TokenEndpointAuthMethod] = Field(
        default_factory=lambda: list(TokenEndpointAuthMethod),
        description="How clients may authenticate at the token endpoint",
    )
    scopes_supported: list[str] = Field(default=["mcp"], description="Scopes a client may request")
    authorization_response_iss_parameter_supported: bool = Field(
        default=True,
        description="Every authorization response carries the issuer in 'iss' (RFC 9207), "
        "which clients must compare with this document's issuer",
    )
    client_id_metadata_document_supported: bool = Field(
        default=True,
        description="A client may use the https URL of its metadata document as its "
        "client_id instead of registering",
    )

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
