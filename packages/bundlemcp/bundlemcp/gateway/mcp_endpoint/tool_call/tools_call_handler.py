"""The tools/call method: resolve the presented tool, then run the call pipeline."""

from fastapi import Response
from mcp.shared.inbound import ERROR_CODE_HTTP_STATUS, validate_mcp_param_headers
from mcp.types import INVALID_PARAMS

from bundlemcp.gateway.dialect import Era
from bundlemcp.gateway.mcp_endpoint.jsonrpc import rpc_error
from bundlemcp.gateway.mcp_endpoint.jsonrpc_message import JsonRpcMessage
from bundlemcp.gateway.mcp_endpoint.request_context import RequestContext
from bundlemcp.gateway.mcp_endpoint.tool_call.audit_context import AuditContext
from bundlemcp.gateway.mcp_endpoint.tool_call.tool_call import ToolCall
from bundlemcp.gateway.mcp_endpoint.tool_call.tool_call_support import ToolCallSupport
from bundlemcp.models import AuditStatus


class ToolsCallHandler:
    def __init__(self, support: ToolCallSupport) -> None:
        self._support = support

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        presented_name = message.param("name", "")
        tool = ctx.view.resolve(presented_name)
        if tool is None:
            # TM-2: disabled/unknown tools are rejected on call, not just hidden
            audit = AuditContext.for_request(ctx, presented_name)
            self._support.audit.record(
                audit.record(AuditStatus.DENIED, denied_reason="unknown_or_disabled_tool")
            )
            return rpc_error(message.id, INVALID_PARAMS, f"Unknown tool: {presented_name}")
        if ctx.era is Era.MODERN:
            # PROT-15: every Mcp-Param-* header must agree with the argument it mirrors.
            rejection = validate_mcp_param_headers(
                tool.input_schema,
                message.param("arguments", {}),
                {name.lower(): value for name, value in ctx.request.headers.items()},
            )
            if rejection is not None:
                return rpc_error(
                    message.id,
                    rejection.code,
                    rejection.message,
                    status=ERROR_CODE_HTTP_STATUS.get(rejection.code, 400),
                    data=rejection.data,
                )
        return await ToolCall(self._support, ctx, message, tool).run()
