from typing import Any

from pydantic import BaseModel, Field


class CallOutcome(BaseModel):
    """What a proxied tools/call produced, before it is rendered as JSON-RPC."""

    status: str = Field(description="How the call ended: 'success' or 'error'")
    result: Any = Field(
        default=None, description="The upstream CallToolResult when the call succeeded"
    )
    error_message: str | None = Field(
        default=None, description="Human-readable failure text when the call did not succeed"
    )
    code: int | None = Field(default=None, description="JSON-RPC error code to report, if any")
