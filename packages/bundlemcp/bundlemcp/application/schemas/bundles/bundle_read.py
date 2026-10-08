import uuid
from datetime import datetime

from pydantic import Field

from bundlemcp.application.schemas.common.entity_read import EntityRead


class BundleRead(EntityRead):
    """A bundle as stored."""

    id: uuid.UUID = Field(description="Identifier of the bundle")
    name: str = Field(description="Unique bundle name")
    description: str | None = Field(description="Free-text note about what this bundle is for")
    overview: str | None = Field(  # BND-11
        description="Long-form description of the bundle for people browsing the "
        "catalogue: what it is for, what the tools can do, and anything a user must set "
        "up first. Plain text, paragraphs separated by blank lines. Unlike 'description' "
        "this is never sent to a model, so it can be as long as it needs to be"
    )
    created_at: datetime = Field(description="When the bundle was created")
    updated_at: datetime = Field(description="When the bundle was last changed")
