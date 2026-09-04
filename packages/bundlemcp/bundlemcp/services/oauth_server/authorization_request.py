from pydantic import BaseModel, ConfigDict, Field


class AuthorizationRequest(BaseModel):
    """The query parameters of GET /oauth/authorize, as received."""

    model_config = ConfigDict(frozen=True)

    client_id: str = Field(default="", description="Client asking for access")
    redirect_uri: str = Field(default="", description="Where the client wants the code sent")
    response_type: str | None = Field(default=None, description="Must be 'code'")
    state: str | None = Field(default=None, description="Opaque value echoed back to the client")
    scope: str | None = Field(
        default=None, description="Scopes requested; the client's default if absent"
    )
    code_challenge: str = Field(default="", description="PKCE S256 challenge")
    code_challenge_method: str = Field(default="S256", description="Only S256 is accepted")
    resource: str = Field(
        default="", description="Resource identifier naming the endpoint the token is for"
    )
