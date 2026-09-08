import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from bundlemcp.domain.shared.clock import utcnow


class Bundle(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Identifier of the bundle")
    name: str = Field(description="Unique bundle name")
    description: str | None = Field(  # BND-1
        default=None,
        description="Free-text note about the bundle, served to clients as MCP instructions",
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        description="When the bundle was created",
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        description="When the bundle was last changed",
    )
