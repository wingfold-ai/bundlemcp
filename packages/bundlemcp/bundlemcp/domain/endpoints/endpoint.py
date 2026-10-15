import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.domain.endpoints.endpoint_profile import EndpointProfile
from bundlemcp.domain.endpoints.origin_policy import (
    default_allowed_origins,
    normalise_allowed_origins,
    origin_allowed,
)
from bundlemcp.domain.shared.clock import utcnow


class Endpoint(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Identifier of the endpoint")
    name: str = Field(
        description="Unique endpoint name; it forms the public URL path segment",
    )
    bundle_id: uuid.UUID = Field(
        description="Bundle this endpoint exposes",
    )
    profile: EndpointProfile = Field(
        default=EndpointProfile.DEFAULT,
        description="Profile shaping how the endpoint serves its bundle",
    )
    auth_modes: list[EndpointAuthMode] = Field(
        default_factory=lambda: [EndpointAuthMode.API_KEY],
        description="Accepted credentials: oauth, api_key, or none for an open endpoint",
    )
    rate_limit: dict[str, Any] | None = Field(
        default=None,
        description="Rate-limit configuration; null when the endpoint is unlimited",
    )
    enabled: bool = Field(
        default=True, description="Whether the endpoint currently serves requests"
    )
    allowed_origins: list[str] = Field(
        description="Browser origins that may use the endpoint from another site, or ['*'] "
        "for any; when omitted, [] for an open endpoint and ['*'] otherwise",
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        description="When the record was created",
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        description="When the record was last changed",
    )

    @model_validator(mode="before")
    @classmethod
    def _default_allowed_origins(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("allowed_origins") is None:
            modes = data.get("auth_modes") or [EndpointAuthMode.API_KEY]
            data = {**data, "allowed_origins": default_allowed_origins(modes)}
        return data

    @field_validator("allowed_origins")
    @classmethod
    def _normalised(cls, value: list[str]) -> list[str]:
        return normalise_allowed_origins(value)

    def allows_origin(self, origin: str, public_origin: str) -> bool:
        """Whether a browser request carrying this ``Origin`` may use the endpoint."""
        return origin_allowed(origin, self.allowed_origins, public_origin)

    def accepts(self, mode: EndpointAuthMode) -> bool:
        return mode in self.auth_modes

    @property
    def is_anonymous_only(self) -> bool:
        """The endpoint takes no credentials at all, so every caller is nobody."""
        return set(self.auth_modes) == {EndpointAuthMode.NONE}
