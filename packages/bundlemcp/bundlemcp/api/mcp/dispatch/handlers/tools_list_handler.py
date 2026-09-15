from typing import Any

from fastapi import Response

from bundlemcp.api.mcp.protocol.cache_hints import CacheHints
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_result
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.domain.bundles.presented_tool import PresentedTool


class ToolsListHandler:
    """The curated, prefixed tool surface of the endpoint's bundle, in a stable order."""

    def __init__(self, cache_hints: CacheHints) -> None:
        self._cache_hints = cache_hints

    @staticmethod
    def _entry(tool: PresentedTool) -> dict[str, Any]:
        entry: dict[str, Any] = {"name": tool.presented_name, "inputSchema": tool.input_schema}
        if tool.title:
            entry["title"] = tool.title
        if tool.description:
            entry["description"] = tool.description
        if tool.annotations:
            entry["annotations"] = tool.annotations
        return entry

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        result = {"tools": [self._entry(t) for t in ctx.view.tools]}
        return rpc_result(message.id, ctx.shape(result, await self._cache_hints.for_list()))
