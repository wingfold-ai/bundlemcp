from pydantic import BaseModel


class UpstreamOAuthConfig(BaseModel):
    """Pre-registered upstream OAuth client + optional explicit endpoints."""

    client_id: str
    client_secret: str | None = None  # write-only
    authorization_url: str | None = None
    token_url: str | None = None
