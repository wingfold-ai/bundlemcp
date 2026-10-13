from fastapi import Response

from bundlemcp.api.mcp.dispatch.handlers.member_fanout import MemberFanout, dump
from bundlemcp.api.mcp.protocol.bundle_content_wire import resource_contents
from bundlemcp.api.mcp.protocol.cache_hints import CacheHints
from bundlemcp.api.mcp.protocol.dialect import NeutralError
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_error, rpc_result
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.application.serving.bundle_content_reader import BundleContentReader
from bundlemcp.domain.bundles.bundle_resource_uri import bundle_resource_name, is_bundle_uri
from bundlemcp.domain.servers.server_capability import ServerCapability


class ResourcesReadHandler:
    """Serve a bundle URI here; otherwise resolve the owner by asking each member, and the
    first that serves the URI wins."""

    def __init__(
        self, fanout: MemberFanout, content: BundleContentReader, cache_hints: CacheHints
    ) -> None:
        self._fanout = fanout
        self._content = content
        self._cache_hints = cache_hints

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        uri = message.param("uri", "")
        if is_bundle_uri(uri):
            # BND-26: the bundle's own scheme never falls through to a member
            return await self._bundle_resource(ctx, message, uri)
        # BND-8
        result = await self._fanout.first(
            ctx,
            lambda client: client.read_resource_mcp(uri),
            capability=ServerCapability.RESOURCES,
        )
        if result is None:
            return self._not_found(ctx, message, uri)
        payload = dump(result)
        return rpc_result(message.id, ctx.shape(payload, CacheHints.for_read(payload)))

    async def _bundle_resource(
        self, ctx: RequestContext, message: JsonRpcMessage, uri: str
    ) -> Response:
        name = bundle_resource_name(uri)
        resource = None
        if name is not None and ctx.view.resource(name) is not None:
            resource = await self._content.resource(ctx.view.bundle.id, name)
        if resource is None:
            return self._not_found(ctx, message, uri)
        payload = {"contents": [resource_contents(resource)]}
        hint = await self._cache_hints.for_bundle_resource()  # BND-29
        return rpc_result(message.id, ctx.shape(payload, hint))

    @staticmethod
    def _not_found(ctx: RequestContext, message: JsonRpcMessage, uri: str) -> Response:
        # PROT-16: -32002 for handshake clients, -32602 for modern ones.
        code = ctx.dialect.error_code(NeutralError.RESOURCE_NOT_FOUND)
        return rpc_error(message.id, code, f"resource not found: {uri}", data={"uri": uri})
