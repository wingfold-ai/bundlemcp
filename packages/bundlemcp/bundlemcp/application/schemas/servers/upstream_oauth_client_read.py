from pydantic import BaseModel, Field


class UpstreamOAuthClientRead(BaseModel):
    """The stored upstream OAuth client registration, secret withheld."""

    server: str = Field(description="Server the client is registered for")
    client_id: str = Field(description="Client id at the upstream authorization server")
    has_secret: bool = Field(
        description="Whether a client secret is stored. The secret itself is never returned"
    )
