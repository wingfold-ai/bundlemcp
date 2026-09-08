from pydantic import BaseModel, Field


class ClientRegistrationRequest(BaseModel):
    """Body for dynamic client registration (RFC 7591)."""

    redirect_uris: list[str] = Field(
        min_length=1,
        description="URIs the authorization response may be sent to. Each must be https, or "
        "http on localhost for a native or development client",
    )
    client_name: str | None = Field(
        default=None, description="Name shown to the user on the consent screen"
    )
    token_endpoint_auth_method: str = Field(
        default="none",
        pattern=r"^(none|client_secret_basic|client_secret_post)$",
        description="How the client authenticates at the token endpoint: 'none' for a public "
        "client, otherwise client_secret_basic or client_secret_post",
    )
    grant_types: list[str] = Field(
        default_factory=lambda: ["authorization_code", "refresh_token"],
        description="Grant types the client intends to use",
    )
    response_types: list[str] = Field(
        default_factory=lambda: ["code"],
        description="Response types the client intends to use",
    )
    scope: str = Field(default="mcp", description="Space-separated scopes requested")
    application_type: str | None = Field(  # OAS-2
        default=None,
        pattern=r"^(web|native)$",
        description="'web' for a browser-hosted client, 'native' for an installed one; MCP "
        "clients registering dynamically state it so redirect URIs are validated accordingly",
    )
