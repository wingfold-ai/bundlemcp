import uuid

from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.access.caller_identity import CallerIdentity


class ResolvedBearer(BaseModel):
    """A valid endpoint access token: whose it is, and which endpoint it was issued for."""

    model_config = ConfigDict(frozen=True)

    identity: CallerIdentity = Field(description="The user the token was issued to")
    endpoint_id: uuid.UUID = Field(description="The one endpoint the token is valid on")
