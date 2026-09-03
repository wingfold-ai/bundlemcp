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
    error_message: str | None = Field(
        default=None, description="Human-readable failure text when the call did not succeed"
    )
    code: int | None = Field(default=None, description="JSON-RPC error code to report, if any")

    @property
    def reached_upstream(self) -> bool:
        """The upstream answered, even if with an error result."""
        return self.result is not None

    def jsonrpc(self, rpc_id: Any) -> dict[str, Any]:
        """The message the client receives for this outcome."""
        if self.result is not None:
            payload = self.result.model_dump(by_alias=True, mode="json", exclude_none=True)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": payload}
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {
                "code": self.code or UPSTREAM_FAILURE,
                "message": self.error_message or "call failed",
            },
        }
