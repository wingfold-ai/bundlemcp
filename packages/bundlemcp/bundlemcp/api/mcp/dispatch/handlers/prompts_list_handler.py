from typing import Any

from fastapi import Response

from bundlemcp.api.mcp.dispatch.handlers.member_fanout import MemberFanout
from bundlemcp.api.mcp.protocol.bundle_content_wire import prompt_entry
from bundlemcp.api.mcp.protocol.cache_hints import CacheHints
from bundlemcp.api.mcp.protocol.curated_entry import curated_entry
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_result
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.domain.bundles.member_entry_ref import MemberEntryRef
from bundlemcp.domain.bundles.presented_name import PresentedName
from bundlemcp.domain.servers.listing_kind import ListingKind
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.member_entry_kind import MemberEntryKind


class PromptsListHandler:
    """The bundle's own prompts, then every member's, each member prompt prefixed with its
    server and curated as the bundle says."""

    def __init__(self, fanout: MemberFanout, cache_hints: CacheHints) -> None:
        self._fanout = fanout
        self._cache_hints = cache_hints

    @staticmethod
    def _presented(
        ctx: RequestContext, server: McpServer, entry: dict[str, Any]
    ) -> dict[str, Any] | None:
        """The member prompt as this bundle presents it, prefixed and curated; None if hidden."""
        ref = MemberEntryRef(
            kind=MemberEntryKind.PROMPT, server_name=server.name, key=entry["name"]
        )
        entry["name"] = PresentedName(server=server.name, name=entry["name"]).text
        return curated_entry(ctx.view.member_curation(ref), entry)

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        # the bundle's own first, in name order; their names have no `__`,
        # so they cannot collide with a prefixed member prompt
        prompts = [prompt_entry(prompt) for prompt in ctx.view.prompts]
        prompts += await self._fanout.merged(
            ctx,
            lambda client: client.list_prompts(),
            listing=ListingKind.PROMPTS,
            present=lambda server, entry: self._presented(ctx, server, entry),
        )
        return rpc_result(
            message.id, ctx.shape({"prompts": prompts}, await self._cache_hints.for_list())
        )
