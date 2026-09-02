import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EndpointRead(BaseModel):
    """An endpoint as stored."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Identifier of the endpoint")
    name: str = Field(description="Unique endpoint name; it forms the URL path segment")
    bundle_id: uuid.UUID = Field(description="Bundle this endpoint exposes")
    profile: str = Field(
        description="Client profile shaping the responses, such as the claude or chatgpt profile"
    )
    auth_modes: list[str] = Field(
        description="Accepted credentials: oauth, api_key, or none for an open endpoint"
    )
    rate_limit: dict[str, Any] | None = Field(
        description="Rate-limit configuration; null when the endpoint is unlimited"
    )
    enabled: bool = Field(description="Whether the endpoint currently serves requests")
    created_at: datetime = Field(description="When the endpoint was created")
    updated_at: datetime = Field(description="When the endpoint was last changed")
