from pydantic import BaseModel, Field


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
    resource_scopes: list[str] = Field(  # UPO-1
        default=[],
        description="Scopes the protected resource asks clients to request: the 'scope' of its "
        "WWW-Authenticate challenge, else the scopes_supported of its resource metadata",
    )
    issuer: str | None = Field(  # UPO-8
        default=None,
        description="The authorization server's issuer identifier from its metadata, which an "
        "'iss' on the authorization response must equal",
    )
    authorization_response_iss_parameter_supported: bool = Field(  # UPO-8
        default=False,
        description="Whether the server promises an 'iss' on every authorization response, in "
        "which case a response without one is refused",
    )

    @property
    def authorization_scope(self) -> str | None:
        """The scope to request at authorization, or None to leave the choice to the server.

        Only what the protected resource asks for is requested. An authorization
        server's own catalogue lists scopes the client was never granted, and a
        server refuses the whole request over one of them.
        """
        return " ".join(self.resource_scopes) or None
