from fastapi import Response

from bundlemcp.gateway.mcp_endpoint.endpoint_context import EndpointContext
from bundlemcp.gateway.mcp_endpoint.jsonrpc_message import JsonRpcMessage
from bundlemcp.gateway.mcp_endpoint.method_handler import MethodHandler
from bundlemcp.gateway.mcp_endpoint.rate_limit_gate import RateLimitGate


class RateLimited[C: EndpointContext]:
    """A handler that first asks the rate-limit gate, then defers to the one it wraps."""

    def __init__(self, inner: MethodHandler[C], gate: RateLimitGate, *, tool_call: bool) -> None:
        self._inner = inner
        self._gate = gate
        self._tool_call = tool_call

    async def handle(self, ctx: C, message: JsonRpcMessage) -> Response:
        limited = await self._gate.check(ctx, message, tool_call=self._tool_call)
        if limited is not None:
            return limited
        return await self._inner.handle(ctx, message)
