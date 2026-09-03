from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.gateway.composition import BundleView
from bundlemcp.models import CallerIdentity


class EndpointContext(BaseModel):
    """What is known about a request once its endpoint is resolved and its caller admitted."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    request: Request = Field(description="The HTTP request, for headers and the client address")
    view: BundleView = Field(description="The endpoint being served and its presented tools")
    identity: CallerIdentity = Field(description="Who is calling")
