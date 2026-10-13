from pydantic import BaseModel, Field

from bundlemcp.domain.bundles.bundle_resource_uri import bundle_resource_uri
from bundlemcp.domain.bundles.resource_mime_type import ResourceMimeType
from bundlemcp.domain.shared.resource_names import BundleResourceName


class ResourceListing(BaseModel):
    """What a client learns about a bundle resource before reading it: everything but its
    content."""

    name: BundleResourceName = Field(  # BND-23
        description="Resource name, unique in its bundle; '/' separates folders, as in "
        "'guides/style'"
    )
    title: str | None = Field(default=None, description="Human-readable title")
    description: str | None = Field(default=None, description="What the resource contains")
    mime_type: ResourceMimeType = Field(
        default=ResourceMimeType.MARKDOWN, description="Text format of the content"
    )
    size_bytes: int = Field(default=0, ge=0, description="Size of the content, in UTF-8 bytes")

    @property
    def uri(self) -> str:
        """The URI a client reads the resource by."""
        return bundle_resource_uri(self.name)
