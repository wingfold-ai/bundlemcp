from fastapi import Response

from bundlemcp.api.mcp.dispatch.handlers.member_fanout import MemberFanout
from bundlemcp.api.mcp.protocol.cache_hints import CacheHints
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_result
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.domain.servers.server_capability import ServerCapability


class ResourcesListHandler:
    """Every member's resources; URIs pass through unchanged, de-duplicated by URI."""

    def __init__(self, fanout: MemberFanout, cache_hints: CacheHints) -> None:
        self._fanout = fanout
        self._cache_hints = cache_hints

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        # BND-8
        items = await self._fanout.merged(
            ctx,
            lambda client: client.list_resources(),
            capability=ServerCapability.RESOURCES,
            key="uri",
        )
        return rpc_result(
            message.id, ctx.shape({"resources": items}, await self._cache_hints.for_list())
        )
