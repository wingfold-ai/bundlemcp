import uuid

from pydantic import BaseModel, Field


class MemberEntryCuration(BaseModel):
    """How one bundle presents a member's prompt or resource.

    Absent curation serves the entry unchanged. A disabled entry is neither
    listed nor fetched for this bundle; the overrides replace what the member
    reports as title and description. The name, URI and content never change.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Identifier of the curation")
    bundle_id: uuid.UUID = Field(description="Bundle this curation applies to")
    entry_id: uuid.UUID = Field(description="The cached member entry it curates")
    enabled: bool = Field(default=True, description="Whether the bundle serves the entry")
    override_title: str | None = Field(default=None, description="Title presented instead")
    override_description: str | None = Field(
        default=None, description="Description presented instead"
    )
