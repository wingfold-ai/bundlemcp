from fastapi import Response

from bundlemcp.gateway.mcp_endpoint.handlers.member_fanout import MemberFanout, dump
from bundlemcp.gateway.mcp_endpoint.jsonrpc import rpc_error, rpc_result
from bundlemcp.gateway.mcp_endpoint.jsonrpc_message import JsonRpcMessage
from bundlemcp.gateway.mcp_endpoint.session_context import SessionContext

RESOURCE_NOT_FOUND = -32002


class ResourcesReadHandler:
    """Resolve the owner by asking each member; the first that serves the URI wins."""

    def __init__(self, fanout: MemberFanout) -> None:
        self._fanout = fanout

    async def handle(self, ctx: SessionContext, message: JsonRpcMessage) -> Response:
        # BND-8
        uri = message.param("uri", "")
        result = await self._fanout.first(ctx, lambda client: client.read_resource_mcp(uri))
        if result is None:
            return rpc_error(message.id, RESOURCE_NOT_FOUND, f"resource not found: {uri}")
        return rpc_result(message.id, dump(result))
