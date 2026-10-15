"""What the bundle offers a modern-era client, answered without reaching any member."""

from fastapi import Response

from bundlemcp.api.mcp.protocol.cache_hints import CacheHints
from bundlemcp.api.mcp.protocol.dialect import DialectRegistry
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_result
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.domain.bundles.bundle_capabilities import aggregate_capabilities


class ServerDiscoverHandler:
    def __init__(
        self, dialects: DialectRegistry, cache_hints: CacheHints, *, member_notifications: bool
    ) -> None:
        # member_notifications: whether members' list changes and resource
        # updates reach clients, which decides whether they are advertised
        self._dialects = dialects
        self._cache_hints = cache_hints
        self._member_notifications = member_notifications

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        # versions from the registry, capabilities from the discovery snapshots.
        result = {
            "supportedVersions": self._dialects.modern_versions,
            "capabilities": aggregate_capabilities(
                ctx.view, member_notifications=self._member_notifications
            ),
        }
        if ctx.view.bundle.description:
            result["instructions"] = ctx.view.bundle.description
        return rpc_result(message.id, ctx.shape(result, await self._cache_hints.for_list()))
