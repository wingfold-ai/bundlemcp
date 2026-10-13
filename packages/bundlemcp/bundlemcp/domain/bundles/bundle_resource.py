import uuid
from datetime import datetime
from typing import Self

from pydantic import Field, model_validator

from bundlemcp.domain.bundles.resource_listing import ResourceListing
from bundlemcp.domain.shared.clock import utcnow


class BundleResource(ResourceListing):
    """A text document authored on a bundle and served by the gateway itself."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Identifier of the resource")
    bundle_id: uuid.UUID = Field(description="Bundle the resource belongs to")
    content: str = Field(description="The document itself")
    created_at: datetime = Field(default_factory=utcnow, description="When it was created")
    updated_at: datetime = Field(default_factory=utcnow, description="When it last changed")

    @model_validator(mode="after")
    def _measure(self) -> Self:
        # The size is derived, never supplied, so it cannot disagree with the content.
        self.size_bytes = len(self.content.encode())
        return self
