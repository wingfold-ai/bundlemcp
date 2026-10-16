from typing import Any

from pydantic import BaseModel, Field

from bundlemcp.application.schemas.inspector.inspector_target import InspectorTarget


class InspectorCallRequest(BaseModel):
    """A tools/call the inspector sends to its target."""

    target: InspectorTarget = Field(
        description="What to connect to: a registered upstream, an endpoint of this gateway, or "
        "an ad-hoc URL, selected by 'kind'"
    )
    tool: str = Field(
        min_length=1,
        description="The tool's name as the target lists it; for an endpoint, the presented "
        "(prefixed) name",
    )
    arguments: dict[str, Any] = Field(
        default_factory=dict, description="The call's arguments, matching the tool's input schema"
    )
