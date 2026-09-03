"""Which handler serves which JSON-RPC method."""

from collections.abc import Mapping

from fastapi import Response

from bundlemcp.gateway.mcp_endpoint.jsonrpc import rpc_error
from bundlemcp.gateway.mcp_endpoint.jsonrpc_message import JsonRpcMessage
from bundlemcp.gateway.mcp_endpoint.method_handler import MethodHandler
from bundlemcp.gateway.mcp_endpoint.session_context import SessionContext

METHOD_NOT_FOUND = -32601


class MethodRegistry:
    """Routes a session-bound message to the handler registered for its method.

    Adding a method means registering a handler, not editing a dispatcher. An
    unregistered notification is acknowledged and dropped, as the protocol asks;
    an unregistered request is answered with method-not-found.
    """

    def __init__(self, handlers: Mapping[str, MethodHandler[SessionContext]]) -> None:
        self._handlers = dict(handlers)

    async def dispatch(self, ctx: SessionContext, message: JsonRpcMessage) -> Response:
        handler = self._handlers.get(message.method or "")
        if handler is not None:
            return await handler.handle(ctx, message)
        if message.is_notification:
            return Response(status_code=202)
        return rpc_error(message.id, METHOD_NOT_FOUND, f"method not supported: {message.method}")
