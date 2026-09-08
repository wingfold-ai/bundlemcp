from pydantic import BaseModel, Field


class ProtectedResourceMetadata(BaseModel):
    """One endpoint as a protected resource, pointing at its authorization server (RFC 9728)."""

    resource: str = Field(description="Canonical resource identifier of the endpoint")
    authorization_servers: list[str] = Field(
        description="Issuers that mint tokens for this resource; always this gateway"
    )
    bearer_methods_supported: list[str] = Field(
        default=["header"], description="Tokens are accepted in the Authorization header only"
    )
    scopes_supported: list[str] = Field(default=["mcp"], description="Scopes a token may carry")
