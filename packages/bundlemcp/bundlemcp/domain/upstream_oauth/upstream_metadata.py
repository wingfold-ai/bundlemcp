from pydantic import BaseModel, Field

from bundlemcp.domain.upstream_oauth.client_identification import ClientIdentification

PKCE_METHOD = "S256"
PUBLIC_CLIENT_AUTH_METHOD = "none"


class UpstreamMetadata(BaseModel):
    """The endpoints of an upstream authorization server, discovered or configured."""

    authorization_endpoint: str = Field(description="Where the user is sent to authorize")
    token_endpoint: str = Field(description="Where authorization codes are exchanged for tokens")
    registration_endpoint: str | None = Field(
        default=None,
        description="Dynamic client registration endpoint, when the server offers one",
    )
    scopes_supported: list[str] = Field(
        default=[],
        description="Scopes the authorization server advertises; its whole catalogue, never "
        "what a client should request",
    )
    resource_scopes: list[str] = Field(  # UPS-25
        default=[],
        description="Scopes the protected resource asks clients to request: the 'scope' of its "
        "WWW-Authenticate challenge, else the scopes_supported of its resource metadata",
    )
    issuer: str | None = Field(  # UPS-32
        default=None,
        description="The authorization server's issuer identifier from its metadata, which an "
        "'iss' on the authorization response must equal",
    )
    authorization_response_iss_parameter_supported: bool = Field(  # UPS-32
        default=False,
        description="Whether the server promises an 'iss' on every authorization response, in "
        "which case a response without one is refused",
    )
    resource: str | None = Field(  # UPS-36
        default=None,
        description="The RFC 8707 resource indicator every authorization, token and refresh "
        "request names: the protected resource's identifier or the server's canonical URL",
    )
    client_id_metadata_document_supported: bool = Field(  # UPS-25
        default=False,
        description="Whether the server accepts a client metadata document URL as a client id",
    )
    token_endpoint_auth_methods_supported: list[str] = Field(
        default=[],
        description="How clients may authenticate at the token endpoint; empty when the "
        "server does not say",
    )
    grant_types_supported: list[str] = Field(
        default=[], description="Grant types the server advertises; empty when it does not say"
    )
    step_up_scopes: list[str] = Field(  # UPS-34
        default=[],
        description="Scopes an upstream later asked for with insufficient_scope, requested on "
        "top of the resource scopes at the next connect",
    )

    @property
    def authorization_scope(self) -> str | None:
        """The scope to request at authorization, or None to leave the choice to the server.

        Only what the protected resource asks for is requested: the scopes it
        named at discovery, plus any it later demanded with insufficient_scope.
        An authorization
        server's own catalogue lists scopes the client was never granted, and a
        server refuses the whole request over one of them.
        """
        scopes = list(dict.fromkeys([*self.resource_scopes, *self.step_up_scopes]))
        return " ".join(scopes) or None

    @property
    def accepts_public_clients(self) -> bool:
        """The token endpoint takes a client that has no secret (or does not say otherwise)."""
        methods = self.token_endpoint_auth_methods_supported
        return not methods or PUBLIC_CLIENT_AUTH_METHOD in methods

    def automatic_identification(self, *, metadata_document_usable: bool) -> ClientIdentification:
        """How the gateway can identify itself here without an admin storing a client.

        A metadata document is preferred, then dynamic registration; the
        gateway's document is only usable when it is served over https.
        """
        if (
            metadata_document_usable
            and self.client_id_metadata_document_supported
            and self.accepts_public_clients
        ):
            return ClientIdentification.METADATA_DOCUMENT
        if self.registration_endpoint:
            return ClientIdentification.DYNAMIC_REGISTRATION
        return ClientIdentification.PREREGISTERED_REQUIRED
