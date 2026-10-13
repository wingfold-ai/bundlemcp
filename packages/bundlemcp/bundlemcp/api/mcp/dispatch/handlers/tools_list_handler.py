from typing import Any

from fastapi import Response

from bundlemcp.api.mcp.protocol.cache_hints import CacheHints
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_result
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.application.upstream_oauth.account_connect_prompts import AccountConnectPrompts
from bundlemcp.domain.bundles.listed_tool import ListedTool


class ToolsListHandler:
    """The curated, prefixed tool surface of the endpoint's bundle, in a stable order.

    A caller who still has to connect their own account to a member server
    also sees that server's connect-account tool, after the bundle's tools.
    """

    def __init__(self, cache_hints: CacheHints, connect_prompts: AccountConnectPrompts) -> None:
        self._cache_hints = cache_hints
        self._connect_prompts = connect_prompts

    @staticmethod
    def _entry(tool: ListedTool) -> dict[str, Any]:
        entry: dict[str, Any] = {"name": tool.presented_name, "inputSchema": tool.input_schema}
        if tool.title:
            entry["title"] = tool.title
        if tool.description:
            entry["description"] = tool.description
        if tool.annotations:
            entry["annotations"] = tool.annotations
        return entry

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        tools: list[ListedTool] = list(ctx.view.tools)
        tools += await self._connect_prompts.pending(ctx.view, ctx.identity)  # UPS-27
        result = {"tools": [self._entry(t) for t in tools]}
        return rpc_result(message.id, ctx.shape(result, await self._cache_hints.for_list()))
