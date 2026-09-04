from typing import Protocol, runtime_checkable

from fastapi import Response

from bundlemcp.gateway.mcp_endpoint.endpoint_context import EndpointContext
from bundlemcp.gateway.mcp_endpoint.jsonrpc_message import JsonRpcMessage


@runtime_checkable
class MethodHandler[C: EndpointContext](Protocol):
    """Serves one JSON-RPC method for a request in context ``C``.

    Handlers for methods that need a live session take a ``SessionContext``;
    the one method that creates the session, initialize, takes the bare
    ``EndpointContext``.
    """

    async def handle(self, ctx: C, message: JsonRpcMessage) -> Response: ...
