"""The tools/call method: resolve the presented tool, then run the call pipeline."""

from fastapi import Response
from mcp.shared.inbound import ERROR_CODE_HTTP_STATUS, validate_mcp_param_headers
from mcp.types import INVALID_PARAMS, InputResponses
from pydantic import TypeAdapter, ValidationError

from bundlemcp.api.mcp.protocol.dialect import ProtocolEra
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_error, rpc_result
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.api.mcp.relay import RequestState, ResumeInputs, StateRejected
from bundlemcp.api.mcp.tool_call.audit_context import AuditContext
from bundlemcp.api.mcp.tool_call.call_outcome import UPSTREAM_FAILURE
from bundlemcp.api.mcp.tool_call.resumed_call import ResumedCall
from bundlemcp.api.mcp.tool_call.tool_call import NO_CIPHER, ToolCall
from bundlemcp.api.mcp.tool_call.tool_call_support import ToolCallSupport
from bundlemcp.application.upstream_oauth.account_connect_prompts import AccountConnectPrompts
from bundlemcp.domain.audit.audit_status import AuditStatus
from bundlemcp.domain.upstream_oauth.connect_account_tool import (
    CONNECT_ACCOUNT_TOOL,
    ConnectAccountTool,
)

input_responses_adapter: TypeAdapter[InputResponses] = TypeAdapter(InputResponses)


class ToolsCallHandler:
    def __init__(self, support: ToolCallSupport, connect_prompts: AccountConnectPrompts) -> None:
        self._support = support
        self._connect_prompts = connect_prompts

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        presented_name = message.param("name", "")
        tool = ctx.view.resolve(presented_name)
        if tool is None:
            connect = self._connect_prompts.resolve(ctx.view, presented_name)
            if connect is not None:
                return self._connect_account(ctx, message, connect)
            # BND-13: disabled/unknown tools are rejected on call, not just hidden
            audit = AuditContext.for_request(ctx, presented_name)
            self._support.audit.record(
                audit.record(AuditStatus.DENIED, denied_reason="unknown_or_disabled_tool")
            )
            return rpc_error(message.id, INVALID_PARAMS, f"Unknown tool: {presented_name}")
        if ctx.era is ProtocolEra.STATELESS:
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
            if message.param("requestState") is not None:
                return await self._retry(ctx, message, tool)
        return await ToolCall(self._support, ctx, message, tool).run()

    # UPS-27
    def _connect_account(
        self, ctx: RequestContext, message: JsonRpcMessage, tool: ConnectAccountTool
    ) -> Response:
        """Answer with the connect link; no upstream is reached and nothing is metered."""
        audit = AuditContext.for_request(ctx, tool.presented_name).model_copy(
            update={"server_name": tool.server.name, "tool_name": CONNECT_ACCOUNT_TOOL}
        )
        self._support.audit.record(audit.record(AuditStatus.SUCCESS))
        text = self._connect_prompts.instructions(tool, ctx.identity)
        result = {"content": [{"type": "text", "text": text}], "isError": False}
        return rpc_result(message.id, ctx.shape(result))

    async def _retry(self, ctx: RequestContext, message: JsonRpcMessage, tool) -> Response:
        # PROT-18
        """The client is answering an earlier input_required result."""
        cipher = self._support.state_cipher
        if cipher is None:
            return rpc_error(message.id, UPSTREAM_FAILURE, NO_CIPHER)
        try:
            state = RequestState.unseal(
                cipher,
                message.param("requestState"),
                presented_tool=message.param("name", ""),
                arguments=message.param("arguments", {}),
                sub=ctx.identity.sub,
            )
            responses = message.param("inputResponses", {})
            input_responses_adapter.validate_python(responses)
        except StateRejected as exc:
            return rpc_error(message.id, INVALID_PARAMS, str(exc), status=400)
        except ValidationError as exc:
            return rpc_error(
                message.id, INVALID_PARAMS, f"invalid inputResponses: {exc}", status=400
            )
        if state.mode == "passthrough":
            return await ToolCall(
                self._support,
                ctx,
                message,
                tool,
                resume=ResumeInputs(responses=responses, upstream_state=state.upstream_state),
                idempotency_key=state.idempotency_key,
            ).run()
        return await ResumedCall(self._support, ctx, message, tool, state, responses).run()
