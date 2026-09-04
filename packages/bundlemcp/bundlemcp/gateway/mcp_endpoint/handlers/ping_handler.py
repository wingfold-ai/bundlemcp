from fastapi import Response

from bundlemcp.gateway.mcp_endpoint.jsonrpc import rpc_result
from bundlemcp.gateway.mcp_endpoint.jsonrpc_message import JsonRpcMessage
from bundlemcp.gateway.mcp_endpoint.session_context import SessionContext


class PingHandler:
    async def handle(self, ctx: SessionContext, message: JsonRpcMessage) -> Response:
        return rpc_result(message.id, {})
