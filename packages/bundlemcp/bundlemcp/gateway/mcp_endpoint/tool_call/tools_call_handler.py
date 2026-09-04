"""The tools/call method: resolve the presented tool, then run the call pipeline."""

from fastapi import Response

from bundlemcp.gateway.mcp_endpoint.jsonrpc import rpc_error
from bundlemcp.gateway.mcp_endpoint.jsonrpc_message import JsonRpcMessage
from bundlemcp.gateway.mcp_endpoint.session_context import SessionContext
from bundlemcp.gateway.mcp_endpoint.tool_call.audit_context import AuditContext
from bundlemcp.gateway.mcp_endpoint.tool_call.tool_call import ToolCall
from bundlemcp.gateway.mcp_endpoint.tool_call.tool_call_support import ToolCallSupport
from bundlemcp.models import AuditStatus

INVALID_PARAMS = -32602


class ToolsCallHandler:
    def __init__(self, support: ToolCallSupport) -> None:
        self._support = support

    async def handle(self, ctx: SessionContext, message: JsonRpcMessage) -> Response:
        presented_name = message.param("name", "")
        tool = ctx.view.resolve(presented_name)
        if tool is None:
            # TM-2: disabled/unknown tools are rejected on call, not just hidden
            audit = AuditContext.for_request(ctx, presented_name)
            self._support.audit.record(
                audit.record(AuditStatus.DENIED, denied_reason="unknown_or_disabled_tool")
            )
            return rpc_error(message.id, INVALID_PARAMS, f"Unknown tool: {presented_name}")
        return await ToolCall(self._support, ctx, message, tool).run()
