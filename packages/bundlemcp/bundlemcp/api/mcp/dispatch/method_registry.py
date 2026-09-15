"""Which handler serves which JSON-RPC method."""

from collections.abc import Mapping

from fastapi import Response

from bundlemcp.api.mcp.dispatch.method_handler import MethodHandler
from bundlemcp.api.mcp.protocol.dialect import NeutralError
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_error
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext


class MethodRegistry:
    """Routes an admitted message to the handler registered for its method.

    Adding a method means registering a handler, not editing a dispatcher. A
    method the client's revision does not define, or that no handler serves, is
    answered with method-not-found in the shape and HTTP status that revision
    prescribes; an unregistered notification is acknowledged and dropped.
    """

    def __init__(self, handlers: Mapping[str, MethodHandler[RequestContext]]) -> None:
        self._handlers = dict(handlers)

    async def dispatch(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        method = message.method or ""
        handler = self._handlers.get(method) if ctx.dialect.allows(method) else None
        if handler is not None:
            return await handler.handle(ctx, message)
        if message.is_notification:
            return Response(status_code=202)
        code = ctx.dialect.error_code(NeutralError.METHOD_NOT_FOUND)
        return rpc_error(
            message.id,
            code,
            f"method not supported: {method}",
            status=ctx.dialect.http_status(code),
        )
