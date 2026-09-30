from pydantic import BaseModel, Field

from bundlemcp.domain.upstream_oauth.client_identification import ClientIdentification


class OAuthInspection(BaseModel):
    """What an OAuth-protected upstream's authorization chain revealed."""

    issuer: str | None = Field(
        default=None, description="Issuer identifier of the server's authorization server"
    )
    authorization_endpoint: str | None = Field(
        default=None, description="Where users are sent to sign in"
    )
    scopes: list[str] = Field(
        default=[], description="Scopes the protected resource asks clients to request"
    )
    client_identification: ClientIdentification | None = Field(
        default=None,
        description="How the gateway can identify itself there without an admin: "
        "'metadata_document' (its own client metadata URL), 'dynamic_registration', or "
        "'preregistered_required' when an admin must register a client and enter it on the "
        "server's page, with the callback URL as redirect URI",
    )
    supports_client_credentials: bool = Field(
        default=False,
        description="Whether the authorization server advertises the client_credentials grant, "
        "for a shared connection that authorizes the gateway itself",
    )
    callback_url: str = Field(
        description="The redirect URI to register when a client must be created by hand"
    )
    problem: str | None = Field(
        default=None,
        description="Why the metadata the server points to cannot be used (issuer mismatch, "
        "no PKCE support, blocked address); null when it can",
    )
