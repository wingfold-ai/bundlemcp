from datetime import datetime

from pydantic import Field

from bundlemcp.application.schemas.common.entity_read import EntityRead
from bundlemcp.domain.bundles.resource_mime_type import ResourceMimeType


class BundleResourceRead(EntityRead):
    """A document the bundle itself serves, as stored."""

    name: str = Field(description="Resource name, unique in the bundle")
    uri: str = Field(description="URI clients read the resource by")
    title: str | None = Field(description="Human-readable title")
    description: str | None = Field(description="What the document contains")
    mime_type: ResourceMimeType = Field(description="Text format of the content")
    size_bytes: int = Field(description="Size of the content, in UTF-8 bytes")
    content: str = Field(description="The document itself")
    created_at: datetime = Field(description="When the resource was created")
    updated_at: datetime = Field(description="When the resource was last changed")
