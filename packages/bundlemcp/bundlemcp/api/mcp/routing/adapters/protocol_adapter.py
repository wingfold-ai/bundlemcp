"""Protocol adapter interface for MCP wire eras."""

from typing import Protocol, runtime_checkable

from fastapi import Response

from bundlemcp.api.mcp.protocol.endpoint_context import EndpointContext
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage


@runtime_checkable
class ProtocolAdapter(Protocol):
    """Handles messages for one MCP protocol era."""

    async def handle_post(
        self, ctx: EndpointContext, message: JsonRpcMessage, endpoint_name: str
    ) -> Response: ...
