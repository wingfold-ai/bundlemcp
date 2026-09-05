from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from bundlemcp.gateway.mcp_endpoint.tool_call.call_status import CallStatus

UPSTREAM_FAILURE = -32000
CANCELLED = -32800


class CallOutcome(BaseModel):
    """What a proxied tools/call produced, before it is rendered as JSON-RPC."""

    status: CallStatus = Field(description="How the call ended")
    result: Any = Field(
        default=None, description="The upstream CallToolResult when the call succeeded"
    )
    input_required: Any = Field(
        default=None,
        description="The upstream's InputRequiredResult when it asked for client input itself",
    )
    error_message: str | None = Field(
        default=None, description="Human-readable failure text when the call did not succeed"
    )
    code: int | None = Field(default=None, description="JSON-RPC error code to report, if any")

    @property
    def reached_upstream(self) -> bool:
        """The upstream answered, even if with an error result or a request for input."""
        return self.result is not None or self.input_required is not None

    def body(self, shape: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        """The result or error member of the client's message, shaped for its revision."""
        if self.result is not None:
            payload = self.result.model_dump(by_alias=True, mode="json", exclude_none=True)
            return {"result": shape(payload)}
        return {
            "error": {
                "code": self.code or UPSTREAM_FAILURE,
                "message": self.error_message or "call failed",
            }
        }

    def jsonrpc(
        self, rpc_id: Any, shape: Callable[[dict[str, Any]], dict[str, Any]]
    ) -> dict[str, Any]:
        """The message the client receives for this outcome, shaped for its revision."""
        return {"jsonrpc": "2.0", "id": rpc_id, **self.body(shape)}
