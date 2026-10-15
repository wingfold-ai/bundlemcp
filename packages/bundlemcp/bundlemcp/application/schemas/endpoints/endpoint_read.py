import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from bundlemcp.application.schemas.common.entity_read import EntityRead
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.domain.endpoints.endpoint_profile import EndpointProfile


class EndpointRead(EntityRead):
    """An endpoint as stored."""

    id: uuid.UUID = Field(description="Identifier of the endpoint")
    name: str = Field(description="Unique endpoint name; it forms the URL path segment")
    bundle_id: uuid.UUID = Field(description="Bundle this endpoint exposes")
    profile: EndpointProfile = Field(
        description="Profile shaping how the endpoint serves its bundle: default, oauth_only or "
        "write_as_read; the profile listing says what each one changes"
    )
    auth_modes: list[EndpointAuthMode] = Field(
        description="Accepted credentials: oauth, api_key, or none for an open endpoint"
    )
    rate_limit: dict[str, Any] | None = Field(
        description="Rate-limit configuration; null when the endpoint is unlimited"
    )
    enabled: bool = Field(description="Whether the endpoint currently serves requests")
    created_at: datetime = Field(description="When the endpoint was created")
    updated_at: datetime = Field(description="When the endpoint was last changed")
