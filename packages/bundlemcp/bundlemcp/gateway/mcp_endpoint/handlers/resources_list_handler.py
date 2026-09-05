from fastapi import Response

from bundlemcp.gateway.mcp_endpoint.cache_hints import CacheHints
from bundlemcp.gateway.mcp_endpoint.handlers.member_fanout import MemberFanout
from bundlemcp.gateway.mcp_endpoint.jsonrpc import rpc_result
from bundlemcp.gateway.mcp_endpoint.jsonrpc_message import JsonRpcMessage
from bundlemcp.gateway.mcp_endpoint.request_context import RequestContext


class ResourcesListHandler:
    """Every member's resources; URIs pass through unchanged, de-duplicated by URI."""

    def __init__(self, fanout: MemberFanout, cache_hints: CacheHints) -> None:
        self._fanout = fanout
        self._cache_hints = cache_hints

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        # BND-8
        items = await self._fanout.merged(ctx, lambda client: client.list_resources(), key="uri")
        return rpc_result(
            message.id, ctx.shape({"resources": items}, await self._cache_hints.for_list())
        )
