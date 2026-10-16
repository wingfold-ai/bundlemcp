from typing import Any, Literal

from pydantic import BaseModel, Field


class InspectorCallOutcome(BaseModel):
    """How a call ended; the 'result' stream event, always the last one."""

    type: Literal["result"] = Field(
        default="result", description="Names the stream event this payload is"
    )
    result: dict[str, Any] | None = Field(
        default=None,
        description="The CallToolResult the target returned, as on the wire ('content', "
        "'structuredContent', 'isError'); absent when it answered with an error",
    )
    is_error: bool = Field(
        description="Whether the call failed: a result with 'isError' true, or a JSON-RPC error"
    )
    error_code: int | None = Field(
        default=None, description="The JSON-RPC error code, when the target answered with one"
    )
    error_message: str | None = Field(
        default=None, description="The JSON-RPC error message, when the target answered with one"
    )
    initialize_ms: int = Field(
        ge=0, description="Milliseconds connecting and initialising took, before the call"
    )
    duration_ms: int = Field(ge=0, description="Milliseconds the call itself took")
