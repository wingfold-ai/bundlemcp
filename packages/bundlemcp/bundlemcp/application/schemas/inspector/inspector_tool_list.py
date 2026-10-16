from pydantic import BaseModel, Field

from bundlemcp.application.schemas.inspector.inspector_tool import InspectorTool


class InspectorToolList(BaseModel):
    """The tools a target lists, with how long listing them took."""

    tools: list[InspectorTool] = Field(description="Every tool, in the target's order")
    initialize_ms: int = Field(
        ge=0, description="Milliseconds connecting and initialising took, before the listing"
    )
    duration_ms: int = Field(ge=0, description="Milliseconds the tools/list requests took")
