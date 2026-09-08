from typing import Any

from fastapi import Response

from bundlemcp.api.mcp.cache_hints import CacheHints
from bundlemcp.api.mcp.handlers.member_fanout import MemberFanout
from bundlemcp.api.mcp.jsonrpc import rpc_result
from bundlemcp.api.mcp.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.request_context import RequestContext
from bundlemcp.domain.bundles.presented_name import PresentedName
from bundlemcp.domain.servers.mcp_server import McpServer


class PromptsListHandler:
    """Every member's prompts, each name prefixed with its server."""

    def __init__(self, fanout: MemberFanout, cache_hints: CacheHints) -> None:
        self._fanout = fanout
        self._cache_hints = cache_hints

    @staticmethod
    def _prefixed(server: McpServer, entry: dict[str, Any]) -> dict[str, Any]:
        entry["name"] = PresentedName(server=server.name, name=entry["name"]).text  # BND-8
        return entry

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        prompts = await self._fanout.merged(
            ctx, lambda client: client.list_prompts(), key="name", present=self._prefixed
        )
        return rpc_result(
            message.id, ctx.shape({"prompts": prompts}, await self._cache_hints.for_list())
        )
