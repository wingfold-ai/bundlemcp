"""What the bundle offers a modern-era client, answered without reaching any member."""

from fastapi import Response

from bundlemcp.api.mcp.cache_hints import CacheHints
from bundlemcp.api.mcp.dialect import DialectRegistry
from bundlemcp.api.mcp.jsonrpc import rpc_result
from bundlemcp.api.mcp.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.request_context import RequestContext
from bundlemcp.domain.bundles.bundle_capabilities import aggregate_capabilities


class ServerDiscoverHandler:
    def __init__(self, dialects: DialectRegistry, cache_hints: CacheHints) -> None:
        self._dialects = dialects
        self._cache_hints = cache_hints

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        # PROT-14: versions from the registry, capabilities from the discovery snapshots.
        result = {
            "supportedVersions": self._dialects.modern_versions,
            "capabilities": aggregate_capabilities(ctx.view),  # PROT-11
        }
        if ctx.view.bundle.description:
            result["instructions"] = ctx.view.bundle.description
        return rpc_result(message.id, ctx.shape(result, await self._cache_hints.for_list()))
