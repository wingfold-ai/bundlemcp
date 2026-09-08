import uuid
from datetime import datetime

from pydantic import Field

from bundlemcp.application.schemas.common.entity_read import EntityRead


class BundleRead(EntityRead):
    """A bundle as stored."""

    id: uuid.UUID = Field(description="Identifier of the bundle")
    name: str = Field(description="Unique bundle name")
    description: str | None = Field(description="Free-text note about what this bundle is for")
    created_at: datetime = Field(description="When the bundle was created")
    updated_at: datetime = Field(description="When the bundle was last changed")
