from pydantic import BaseModel, Field


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
