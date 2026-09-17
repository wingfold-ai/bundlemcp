from pydantic import BaseModel, Field

from bundlemcp.domain.oauth.application_type import ApplicationType
from bundlemcp.domain.oauth.grant_type import GrantType
from bundlemcp.domain.oauth.response_type import ResponseType
from bundlemcp.domain.oauth.token_endpoint_auth_method import TokenEndpointAuthMethod


class ClientRegistrationResponse(BaseModel):
    """The registered client as the client must remember it (RFC 7591 section 3.2.1)."""

    client_id: str = Field(description="Identifier issued to the client")
    client_secret: str | None = Field(
        default=None,
        description="Secret for a confidential client, shown exactly once; absent for a public "
        "client",
    )
    client_name: str | None = Field(default=None, description="Name shown on the consent screen")
    redirect_uris: list[str] = Field(description="URIs the authorization response may be sent to")
    grant_types: list[GrantType] = Field(description="Grant types the client registered for")
    response_types: list[ResponseType] = Field(
        description="Response types the client registered for"
    )
    token_endpoint_auth_method: TokenEndpointAuthMethod = Field(
        description="How the client authenticates at the token endpoint"
    )
    scope: str = Field(description="Space-separated scopes the client may request")
    application_type: ApplicationType | None = Field(
        default=None, description="'web' or 'native' as registered, when the client said"
    )
    authorization_endpoint: str = Field(description="Where to send the user to authorize")
    token_endpoint: str = Field(description="Where to exchange codes and refresh tokens")
