from datetime import datetime

from pydantic import BaseModel, Field

from bundlemcp.domain.oauth.application_type import ApplicationType
from bundlemcp.domain.oauth.grant_type import GrantType
from bundlemcp.domain.oauth.token_endpoint_auth_method import TokenEndpointAuthMethod
from bundlemcp.domain.shared.clock import utcnow


class OAuthClient(BaseModel):
    client_id: str = Field(description="Identifier issued to the client")
    client_secret_hash: str | None = Field(
        default=None,
        description="Hash of the client secret. Null marks a public client, which proves "
        "itself with PKCE instead",
    )
    client_name: str | None = Field(
        default=None, description="Name shown to the user on the consent screen"
    )
    redirect_uris: list[str] = Field(
        default_factory=list,
        description="URIs the authorization response may be sent to",
    )
    grant_types: list[GrantType] = Field(
        default_factory=lambda: [GrantType.AUTHORIZATION_CODE, GrantType.REFRESH_TOKEN],
        description="Grant types this client registered for",
    )
    token_endpoint_auth_method: TokenEndpointAuthMethod = Field(
        default=TokenEndpointAuthMethod.NONE,
        description="How the client authenticates at the token endpoint",
    )
    scope: str = Field(default="mcp", description="Space-separated scopes the client may request")
    application_type: ApplicationType | None = Field(  # OAS-2
        default=None,
        description="'web' or 'native' as the client registered itself; absent when it did not "
        "say or was described by a metadata document",
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        description="When the client registered",
    )
    last_used_at: datetime | None = Field(  # SEC-8
        default=None,
        description="When the client last obtained a token. Clients that never used one are "
        "purged, so abandoned registrations do not accumulate",
    )
