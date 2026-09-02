from pydantic import BaseModel, Field, field_validator, model_validator

from bundlemcp.models import RESERVED_ENDPOINT_NAMES, EndpointAuthMode, EndpointProfile
from bundlemcp.schemas.endpoints.rate_limit_config import RateLimitConfig
from bundlemcp.schemas.validation import validate_name


class EndpointUpsert(BaseModel):
    """Body for creating or replacing an endpoint."""

    name: str = Field(
        description="Unique endpoint name; it becomes the URL path segment clients call"
    )
    bundle_name: str = Field(description="Bundle this endpoint exposes")
    profile: EndpointProfile = Field(
        default=EndpointProfile.DEFAULT,
        description="Client profile shaping the responses for a particular consumer",
    )
    auth_modes: list[EndpointAuthMode] = Field(
        default_factory=lambda: [EndpointAuthMode.API_KEY],
        description="Accepted credentials. 'none' is only valid on its own and additionally "
        "requires allow_unauthenticated",
    )
    rate_limit: RateLimitConfig | None = Field(
        default=None, description="Rate limits for this endpoint; omit for unlimited"
    )
    enabled: bool = Field(
        default=True, description="Whether the endpoint serves requests once saved"
    )
    allow_unauthenticated: bool = Field(  # EP-3
        default=False,
        description="Confirms an intentionally open endpoint. Required whenever auth_modes "
        "is ['none'], so an endpoint is never left unauthenticated by accident",
    )
    force: bool = Field(  # EP-8
        default=False,
        description="Confirm a rename that would otherwise be rejected, accepting that clients "
        "using the old name will break",
    )

    @field_validator("name")
    @classmethod
    def name_rules(cls, v: str) -> str:
        validate_name(v)
        if v.lower() in RESERVED_ENDPOINT_NAMES:
            raise ValueError(f"'{v}' is a reserved endpoint name (EP-1)")
        return v

    @model_validator(mode="after")
    def auth_and_profile_rules(self) -> "EndpointUpsert":
        modes = set(self.auth_modes)
        if not modes:
            raise ValueError("auth_modes must not be empty (EP-3)")
        if EndpointAuthMode.NONE in modes:
            if modes != {EndpointAuthMode.NONE}:
                raise ValueError("'none' is only valid alone (EP-3)")
            if not self.allow_unauthenticated:
                raise ValueError("'none' requires allow_unauthenticated=true (EP-3)")
        # PROF-6 matrix
        if self.profile == EndpointProfile.CLAUDE and modes != {EndpointAuthMode.OAUTH}:
            raise ValueError("claude profile requires auth_modes == ['oauth'] (PROF-6)")
        if self.profile == EndpointProfile.CHATGPT and not modes & {
            EndpointAuthMode.OAUTH,
            EndpointAuthMode.API_KEY,
        }:
            raise ValueError("chatgpt profile requires oauth or api_key (PROF-6)")
        return self
