import uuid
from typing import Any

from pydantic import BaseModel, Field


class ToolCurationRead(BaseModel):
    """How one tool is curated within a bundle, as stored after an update."""

    bundle: str = Field(description="Bundle the curation applies to")
    tool_id: uuid.UUID = Field(description="Tool being curated")
    enabled: bool = Field(description="Whether the tool is served through this bundle")
    presented_name: str = Field(
        description="Name clients now see: the override if set, otherwise 'server__tool'"
    )
    override_name: str | None = Field(description="Replacement name, when one is set")
    override_title: str | None = Field(description="Replacement display title, when one is set")
    override_description: str | None = Field(description="Replacement description, when one is set")
    override_annotations: dict[str, Any] | None = Field(
        description="Replacement MCP annotations, when set"
    )
