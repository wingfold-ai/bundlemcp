from typing import Protocol, runtime_checkable

from fastapi import Response

from bundlemcp.api.mcp.protocol.endpoint_context import EndpointContext
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage


@runtime_checkable
class MethodHandler[C: EndpointContext](Protocol):
    """Serves one JSON-RPC method for a request in context ``C``.

    Handlers for methods that need a live session take a ``RequestContext``;
    the one method that creates the session, initialize, takes the bare
    ``EndpointContext``.
    """

    async def handle(self, ctx: C, message: JsonRpcMessage) -> Response: ...
