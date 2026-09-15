from fastapi import Response

from bundlemcp.api.mcp.protocol.jsonrpc import rpc_result
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext


class PingHandler:
    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        return rpc_result(message.id, ctx.shape({}))
