import uuid
from typing import Any

from pydantic import BaseModel, Field


class BundleTool(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Identifier of the curation")
    bundle_id: uuid.UUID = Field(
        description="Bundle this curation applies to",
    )
    tool_id: uuid.UUID = Field(
        description="Tool being curated",
    )
    enabled: bool = Field(
        default=True, description="Whether the tool is served through this bundle"
    )
    override_name: str | None = Field(
        default=None, description="Replacement name clients see instead of 'server__tool'"
    )
    override_title: str | None = Field(
        default=None, description="Replacement display title for this bundle"
    )
    override_description: str | None = Field(
        default=None, description="Replacement description for this bundle"
    )
    override_annotations: dict[str, Any] | None = Field(
        default=None,
        description="Replacement MCP annotations for this bundle",
    )
