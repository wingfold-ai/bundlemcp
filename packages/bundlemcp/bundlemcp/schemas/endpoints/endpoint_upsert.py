from pydantic import BaseModel, Field, field_validator, model_validator

from bundlemcp.models import RESERVED_ENDPOINT_NAMES, EndpointAuthMode, EndpointProfile
from bundlemcp.schemas.validation import validate_name


class EndpointUpsert(BaseModel):
    name: str
    bundle_name: str
    profile: EndpointProfile = EndpointProfile.DEFAULT
    auth_modes: list[EndpointAuthMode] = Field(default_factory=lambda: [EndpointAuthMode.API_KEY])
    enabled: bool = True
    allow_unauthenticated: bool = False  # EP-3: explicit opt-in for `none`
    force: bool = False  # EP-8 rename acknowledgement

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
