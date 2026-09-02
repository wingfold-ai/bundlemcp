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
        default=[], description="Scopes the authorization server advertises"
    )
