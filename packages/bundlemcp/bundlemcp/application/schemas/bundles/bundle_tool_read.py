import uuid
from typing import Any

from pydantic import BaseModel, Field


class BundleToolRead(BaseModel):
    """A member server's tool with this bundle's curation applied."""

    tool_id: uuid.UUID = Field(description="Identifier of the cached upstream tool")
    server_name: str = Field(description="Server that provides the tool")
    name: str = Field(description="Tool name as the upstream server reports it")
    title: str | None = Field(description="Upstream display title, before any override")
    description: str | None = Field(description="Upstream description, before any override")
    member_enabled: bool = Field(
        description="Whether the owning server's membership is enabled; a disabled member "
        "hides its tools regardless of their own toggle"
    )
    enabled: bool = Field(
        description="Whether this tool is served through the bundle; true unless curated off"
    )
    presented_name: str = Field(
        description="Name clients see: the override if set, otherwise 'server__tool'"
    )
    override_name: str | None = Field(description="Replacement name set on this bundle")
    override_title: str | None = Field(description="Replacement title set on this bundle")
    override_description: str | None = Field(
        description="Replacement description set on this bundle"
    )
    override_annotations: dict[str, Any] | None = Field(
        description="Replacement MCP annotations set on this bundle, such as read-only and "
        "destructive hints"
    )
    stale: bool = Field(
        description="True when the latest successful discovery of the owning server no longer "
        "listed the tool. A stale tool is not served but keeps this curation, and is served "
        "with it again if the server lists it again"
    )
