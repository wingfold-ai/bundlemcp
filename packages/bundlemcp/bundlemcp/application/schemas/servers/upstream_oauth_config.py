from pydantic import BaseModel, Field

from bundlemcp.domain.upstream_oauth.upstream_grant import UpstreamGrant


class UpstreamOAuthConfig(BaseModel):
    """Pre-registered upstream OAuth client + optional explicit endpoints."""

    client_id: str = Field(
        description="Client id registered with the upstream authorization server"
    )
    client_secret: str | None = Field(
        default=None,
        description="Client secret for the upstream authorization server. Write-only; it is "
        "never returned",
    )
    authorization_url: str | None = Field(
        default=None,
        description="Authorization endpoint, when it cannot be discovered automatically",
    )
    token_url: str | None = Field(
        default=None, description="Token endpoint, when it cannot be discovered automatically"
    )
    grant_type: UpstreamGrant = Field(  # UPO-11
        default=UpstreamGrant.AUTHORIZATION_CODE,
        description="How the gateway obtains tokens: 'authorization_code' (a person signs in "
        "through the browser) or 'client_credentials' (the gateway authenticates as this "
        "client, for a shared server that authorizes a machine; requires a client secret)",
    )
