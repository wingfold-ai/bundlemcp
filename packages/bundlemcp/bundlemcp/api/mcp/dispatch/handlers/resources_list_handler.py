import structlog
from fastapi import Response

from bundlemcp.api.mcp.dispatch.handlers.member_fanout import MemberFanout
from bundlemcp.api.mcp.protocol.bundle_content_wire import resource_entry
from bundlemcp.api.mcp.protocol.cache_hints import CacheHints
from bundlemcp.api.mcp.protocol.curated_entry import curated_entry
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_result
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.domain.bundles.bundle_resource_uri import is_bundle_uri
from bundlemcp.domain.bundles.member_entry_ref import MemberEntryRef
from bundlemcp.domain.servers.listing_kind import ListingKind
from bundlemcp.domain.servers.member_entry_kind import MemberEntryKind

log = structlog.get_logger(__name__)


class ResourcesListHandler:
    """The bundle's own resources, then every member's; member URIs pass through unchanged,
    de-duplicated by URI."""

    def __init__(self, fanout: MemberFanout, cache_hints: CacheHints) -> None:
        self._fanout = fanout
        self._cache_hints = cache_hints

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        # the bundle's own first, in name order
        items = [resource_entry(resource) for resource in ctx.view.resources]
        for entry in await self._fanout.merged(
            ctx,
            lambda client: client.list_resources(),
            listing=ListingKind.RESOURCES,
            present=lambda server, entry: curated_entry(
                ctx.view.member_curation(
                    MemberEntryRef(
                        kind=MemberEntryKind.RESOURCE, server_name=server.name, key=entry["uri"]
                    )
                ),
                entry,
            ),
        ):
            if is_bundle_uri(entry.get("uri", "")):
                # the bundle answers its own scheme, so a member's is unreachable
                log.warning("passthrough.bundle_uri_shadowed", uri=entry["uri"])
                continue
            items.append(entry)
        return rpc_result(
            message.id, ctx.shape({"resources": items}, await self._cache_hints.for_list())
        )
