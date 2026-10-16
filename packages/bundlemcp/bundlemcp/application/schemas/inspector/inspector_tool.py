from typing import Any

from pydantic import BaseModel, Field


class InspectorTool(BaseModel):
    """One tool as the target lists it."""

    name: str = Field(description="The name a tools/call uses")
    title: str | None = Field(default=None, description="Display title, when the tool sets one")
    description: str | None = Field(default=None, description="What the tool says it does")
    input_schema: dict[str, Any] = Field(
        default_factory=dict, description="JSON Schema of the tool's arguments"
    )
    output_schema: dict[str, Any] | None = Field(
        default=None, description="JSON Schema of the tool's structured result, when declared"
    )
    annotations: dict[str, Any] | None = Field(
        default=None,
        description="Behaviour hints such as 'readOnlyHint' and 'destructiveHint', as the "
        "target sent them",
    )
