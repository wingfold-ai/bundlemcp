from typing import Any

from pydantic import BaseModel, Field


class ProbedTool(BaseModel):
    """A tool definition as an upstream server reported it, before it is cached."""

    name: str = Field(description="Name as the server knows it")
    title: str | None = Field(default=None, description="Display title, when the server set one")
    description: str | None = Field(default=None, description="Description, when set")
    input_schema: dict[str, Any] = Field(
        default_factory=dict, description="JSON Schema of the arguments"
    )
    annotations: dict[str, Any] | None = Field(
        default=None, description="MCP tool annotations, when the server set any"
    )
