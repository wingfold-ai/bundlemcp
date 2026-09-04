import uuid

from pydantic import BaseModel, ConfigDict, Field


class PendingAuthorization(BaseModel):
    """A validated authorization request waiting for the user's consent."""

    model_config = ConfigDict(frozen=True)

    client_id: str = Field(description="Client asking for access")
    client_name: str = Field(description="What the consent screen calls the client")
    redirect_uri: str = Field(description="Where the code is delivered, already verified")
    state: str | None = Field(default=None, description="Opaque value echoed back to the client")
    scope: str = Field(description="Scopes the code will grant")
    code_challenge: str = Field(description="PKCE challenge the token exchange must satisfy")
    endpoint_id: uuid.UUID = Field(description="Endpoint the resulting token is bound to")
    endpoint_name: str = Field(description="Endpoint name, for the consent screen")
    bundle_name: str = Field(description="Bundle the endpoint exposes, for the consent screen")
    user_id: uuid.UUID = Field(description="The signed-in user who must consent")
