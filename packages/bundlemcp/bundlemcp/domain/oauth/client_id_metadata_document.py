from pydantic import BaseModel, ConfigDict, Field, field_validator

from bundlemcp.domain.oauth.grant_type import GrantType
from bundlemcp.domain.oauth.redirect_uri_rule import InvalidRedirectUri, check_redirect_uri
from bundlemcp.domain.oauth.token_endpoint_auth_method import TokenEndpointAuthMethod


class InvalidClientMetadataDocument(ValueError):
    """The document cannot stand for a client.

    It names another URL, describes a confidential client, or registers a
    redirect URI the gateway does not accept.
    """


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

    @field_validator("grant_types", mode="before")
    @classmethod
    def _drop_unsupported_grant_types(cls, value: object) -> object:
        """Keep only the grants this gateway implements.

        A client lists every grant it can use with any server, so an entry the
        gateway does not implement is not an error; the gateway just never issues
        it. A document left without the authorization code grant is refused at
        the authorize endpoint, not here.
        """
        if not isinstance(value, list):
            return value  # the list type check reports it
        supported = {grant.value for grant in GrantType}
        return [grant for grant in value if grant in supported]  # OAS-13

    def check(self, fetched_from: str) -> None:
        """Refuse a document that may not describe a client of this gateway.

        It must name the URL it was fetched from as its client_id, describe a
        public client, and register only redirect URIs the gateway accepts.
        Raises InvalidClientMetadataDocument with the reason.
        """
        if self.client_id != fetched_from:
            raise InvalidClientMetadataDocument(
                "client metadata document does not name its own URL"
            )
        if self.token_endpoint_auth_method != TokenEndpointAuthMethod.NONE:
            raise InvalidClientMetadataDocument(
                "client metadata documents may only describe public clients"
            )
        for uri in self.redirect_uris:
            try:
                check_redirect_uri(uri)
            except InvalidRedirectUri as exc:
                raise InvalidClientMetadataDocument(str(exc)) from None
