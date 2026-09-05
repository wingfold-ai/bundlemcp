from fastapi import Response

from bundlemcp.gateway.dialect import NeutralError
from bundlemcp.gateway.mcp_endpoint.cache_hints import CacheHints
from bundlemcp.gateway.mcp_endpoint.handlers.member_fanout import MemberFanout, dump
from bundlemcp.gateway.mcp_endpoint.jsonrpc import rpc_error, rpc_result
from bundlemcp.gateway.mcp_endpoint.jsonrpc_message import JsonRpcMessage
from bundlemcp.gateway.mcp_endpoint.request_context import RequestContext


class ResourcesReadHandler:
    """Resolve the owner by asking each member; the first that serves the URI wins."""

    def __init__(self, fanout: MemberFanout) -> None:
        self._fanout = fanout

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        # BND-8
        uri = message.param("uri", "")
        result = await self._fanout.first(ctx, lambda client: client.read_resource_mcp(uri))
        if result is None:
            # PROT-16: -32002 for handshake clients, -32602 for modern ones.
            code = ctx.dialect.error_code(NeutralError.RESOURCE_NOT_FOUND)
            return rpc_error(message.id, code, f"resource not found: {uri}", data={"uri": uri})
        payload = dump(result)
        return rpc_result(message.id, ctx.shape(payload, CacheHints.for_read(payload)))
