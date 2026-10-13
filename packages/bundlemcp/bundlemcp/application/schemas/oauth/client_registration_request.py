from pydantic import BaseModel, Field

from bundlemcp.domain.oauth.application_type import ApplicationType
from bundlemcp.domain.oauth.grant_type import GrantType
from bundlemcp.domain.oauth.response_type import ResponseType
from bundlemcp.domain.oauth.token_endpoint_auth_method import TokenEndpointAuthMethod


class ClientRegistrationRequest(BaseModel):
    """Body for dynamic client registration (RFC 7591)."""

    redirect_uris: list[str] = Field(
        min_length=1,
        description="URIs the authorization response may be sent to. Each must be https, or "
        "http on localhost for a native or development client, and on the operator's "
        "redirect-URI allow-list when one is configured",
    )
    client_name: str | None = Field(
        default=None, description="Name shown to the user on the consent screen"
    )
    token_endpoint_auth_method: TokenEndpointAuthMethod = Field(
        default=TokenEndpointAuthMethod.NONE,
        description="How the client authenticates at the token endpoint: 'none' for a public "
        "client, otherwise client_secret_basic or client_secret_post",
    )
    grant_types: list[GrantType] = Field(
        default_factory=lambda: [GrantType.AUTHORIZATION_CODE, GrantType.REFRESH_TOKEN],
        description="Grant types the client intends to use",
    )
    response_types: list[ResponseType] = Field(
        default_factory=lambda: [ResponseType.CODE],
        description="Response types the client intends to use",
    )
    scope: str = Field(default="mcp", description="Space-separated scopes requested")
    application_type: ApplicationType | None = Field(  # AUTH-2
        default=None,
        description="'web' for a browser-hosted client, 'native' for an installed one; MCP "
        "clients registering dynamically state it so redirect URIs are validated accordingly",
    )
