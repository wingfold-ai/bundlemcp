from typing import Any

from pydantic import BaseModel, Field

from bundlemcp.domain.shared.resource_names import ResourceName


class BundleToolUpdate(BaseModel):
    """Per-bundle tool curation: enable/disable plus name/metadata overrides."""

    enabled: bool = Field(
        default=True, description="Whether this tool is served through the bundle"
    )
    override_name: ResourceName | None = Field(
        default=None,
        description="Replacement name clients see instead of 'server__tool'; must still be "
        "unique within the bundle",
    )
    override_title: str | None = Field(
        default=None, description="Replacement display title for this bundle"
    )
    override_description: str | None = Field(
        default=None,
        description="Replacement description for this bundle, for tailoring what the calling "
        "model is told about the tool",
    )
    override_annotations: dict[str, Any] | None = Field(
        default=None, description="Replacement MCP annotations for this bundle"
    )
