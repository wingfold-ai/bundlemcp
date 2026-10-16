from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.shared.resource_names import ResourceName


class BootstrapCuration(BaseModel):
    """How a bundle presents one of a member's tools, the tool named as its upstream names it."""

    model_config = ConfigDict(extra="forbid")

    tool: str = Field(min_length=1, description="The tool's name as the upstream lists it")
    enabled: bool = Field(default=True, description="Whether the bundle serves the tool")
    override_name: ResourceName | None = Field(
        default=None, description="Name the bundle presents instead of the prefixed one"
    )
    override_title: str | None = Field(default=None, description="Title shown instead")
    override_description: str | None = Field(default=None, description="Description shown instead")
    override_annotations: dict[str, Any] | None = Field(
        default=None, description="Annotations presented instead of the upstream's"
    )


class BootstrapMember(BaseModel):
    """A bundle's member, with its enable flag and the curation of its tools."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="Name of the member upstream server")
    enabled: bool = Field(default=True, description="Whether the bundle serves this member")
    tools: list[BootstrapCuration] = Field(
        default=[],
        description="Curation of the member's tools; a tool not listed keeps what is stored, "
        "or the default when nothing is",
    )
