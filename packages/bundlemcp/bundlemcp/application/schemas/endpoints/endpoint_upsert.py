from pydantic import BaseModel, Field, field_validator, model_validator

from bundlemcp.application.schemas.endpoints.rate_limit_config import RateLimitConfig
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.domain.endpoints.endpoint_profile import EndpointProfile
from bundlemcp.domain.endpoints.origin_policy import normalise_allowed_origins
from bundlemcp.domain.shared.resource_names import EndpointName


class EndpointUpsert(BaseModel):
    """Body for creating or replacing an endpoint."""

    name: EndpointName = Field(
        description="Unique endpoint name; it becomes the URL path segment clients call"
    )
    bundle_name: str = Field(description="Bundle this endpoint exposes")
    profile: EndpointProfile = Field(
        default=EndpointProfile.DEFAULT,
        description="Profile shaping how the endpoint serves its bundle: default, oauth_only or "
        "write_as_read; the profile listing says what each one changes",
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
    allowed_origins: list[str] | None = Field(
        default=None,
        max_length=50,
        description="Browser origins (e.g. 'https://app.example') whose pages may call this "
        "endpoint from another site, or ['*'] for any site. Not authentication: clients that "
        "are not browsers are unaffected, and every caller still authenticates per auth_modes. "
        "A browser request from any other origin is refused with 403. Omit for the default: "
        "[] when auth_modes is ['none'], ['*'] otherwise",
    )
    allow_unauthenticated: bool = Field(
        default=False,
        description="Confirms an intentionally open endpoint. Required whenever auth_modes "
        "is ['none'], so an endpoint is never left unauthenticated by accident",
    )
    force: bool = Field(
        default=False,
        description="Confirm a rename that would otherwise be rejected, accepting that clients "
        "using the old name will break",
    )

    @field_validator("allowed_origins")
    @classmethod
    def origins_are_origins(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else normalise_allowed_origins(value)

    @model_validator(mode="after")
    def auth_mode_rules(self) -> EndpointUpsert:
        modes = set(self.auth_modes)
        if not modes:
            raise ValueError("auth_modes must not be empty (EP-3)")
        if EndpointAuthMode.NONE in modes:
            if modes != {EndpointAuthMode.NONE}:
                raise ValueError("'none' is only valid alone (EP-3)")
            if not self.allow_unauthenticated:
                raise ValueError("'none' requires allow_unauthenticated=true (EP-3)")
        # a profile's own rule is checked by the endpoint service against the profile catalogue
        return self
