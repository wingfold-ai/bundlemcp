from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.oauth.grant_type import GrantType
from bundlemcp.domain.oauth.token_endpoint_auth_method import TokenEndpointAuthMethod


class ClientIdMetadataDocument(BaseModel):
    """A client's self-published metadata, fetched from the URL it uses as its client_id."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    client_id: str = Field(description="Must equal the URL the document was fetched from")
    client_name: str | None = Field(default=None, description="Name shown on the consent screen")
    client_uri: str | None = Field(default=None, description="The client's home page")
    redirect_uris: list[str] = Field(
        min_length=1, description="URIs the authorization response may be sent to"
    )
    token_endpoint_auth_method: TokenEndpointAuthMethod = Field(
        default=TokenEndpointAuthMethod.NONE,
        description="How the client authenticates at the token endpoint; only 'none' is "
        "accepted, such clients prove themselves with PKCE",
    )
    grant_types: list[GrantType] = Field(
        default_factory=lambda: [GrantType.AUTHORIZATION_CODE, GrantType.REFRESH_TOKEN],
        description="Grant types the client intends to use",
    )
    scope: str | None = Field(default=None, description="Space-separated scopes requested")
