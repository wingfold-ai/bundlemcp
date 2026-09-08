from pydantic import BaseModel, Field

from bundlemcp.domain.endpoints.endpoint_profile import EndpointProfile


class EndpointProfileRead(BaseModel):
    """One of the client profiles an endpoint can be shaped for."""

    name: EndpointProfile = Field(description="Profile identifier to use in an endpoint's profile")
    description: str = Field(description="What the profile changes about the served surface")
    warning: str | None = Field(
        default=None,
        description="A caveat operators should know before choosing this profile, if any",
    )
