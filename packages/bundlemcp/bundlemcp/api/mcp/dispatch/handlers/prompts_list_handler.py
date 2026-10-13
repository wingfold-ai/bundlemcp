from typing import Any

from fastapi import Response

from bundlemcp.api.mcp.dispatch.handlers.member_fanout import MemberFanout
from bundlemcp.api.mcp.protocol.bundle_content_wire import prompt_entry
from bundlemcp.api.mcp.protocol.cache_hints import CacheHints
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_result
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.domain.bundles.presented_name import PresentedName
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.server_capability import ServerCapability


class PromptsListHandler:
    """The bundle's own prompts, then every member's, each member prompt prefixed with its
    server."""

    def __init__(self, fanout: MemberFanout, cache_hints: CacheHints) -> None:
        self._fanout = fanout
        self._cache_hints = cache_hints

    @staticmethod
    def _prefixed(server: McpServer, entry: dict[str, Any]) -> dict[str, Any]:
        entry["name"] = PresentedName(server=server.name, name=entry["name"]).text
        return entry

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        # the bundle's own first, in name order; their names have no `__`,
        # so they cannot collide with a prefixed member prompt
        prompts = [prompt_entry(prompt) for prompt in ctx.view.prompts]
        prompts += await self._fanout.merged(
            ctx,
            lambda client: client.list_prompts(),
            capability=ServerCapability.PROMPTS,
            key="name",
            present=self._prefixed,
        )
        return rpc_result(
            message.id, ctx.shape({"prompts": prompts}, await self._cache_hints.for_list())
        )
