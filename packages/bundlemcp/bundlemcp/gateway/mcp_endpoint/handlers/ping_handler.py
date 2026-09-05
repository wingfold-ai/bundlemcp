from fastapi import Response

from bundlemcp.gateway.mcp_endpoint.jsonrpc import rpc_result
from bundlemcp.gateway.mcp_endpoint.jsonrpc_message import JsonRpcMessage
from bundlemcp.gateway.mcp_endpoint.request_context import RequestContext


class PingHandler:
    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        return rpc_result(message.id, ctx.shape({}))
