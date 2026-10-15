from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.api.mcp.protocol.cors_grant import CorsGrant
from bundlemcp.domain.access.caller_identity import CallerIdentity
from bundlemcp.domain.bundles.bundle_view import BundleView


class EndpointContext(BaseModel):
    """What is known about a request once its endpoint is resolved and its caller admitted."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    request: Request = Field(description="The HTTP request, for headers and the client address")
    view: BundleView = Field(description="The endpoint being served and its presented tools")
    identity: CallerIdentity = Field(description="Who is calling")
    cors: CorsGrant = Field(
        default_factory=CorsGrant, description="The CORS answer for the request's browser origin"
    )
