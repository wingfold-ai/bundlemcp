from typing import Any

from fastapi import Response

from bundlemcp.api.mcp.dispatch.handlers.input_required_bridge import (
    BridgedRead,
    InputRequiredBridge,
)
from bundlemcp.api.mcp.dispatch.handlers.member_fanout import MemberFanout, dump
from bundlemcp.api.mcp.protocol.bundle_content_wire import resource_contents
from bundlemcp.api.mcp.protocol.cache_hints import CacheHints
from bundlemcp.api.mcp.protocol.dialect import NeutralError, ProtocolEra
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_error, rpc_result
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.application.serving.bundle_content_reader import BundleContentReader
from bundlemcp.domain.bundles.bundle_resource_uri import bundle_resource_name, is_bundle_uri
from bundlemcp.domain.bundles.member_entry_ref import MemberEntryRef
from bundlemcp.domain.servers.member_entry_kind import MemberEntryKind
from bundlemcp.domain.servers.server_capability import ServerCapability


class ResourcesReadHandler:
    """Serve a bundle URI here; otherwise resolve the owner by asking each member, and the
    first that serves the URI wins.

    A modern client's read goes through the input-required bridge, so a member
    that needs client input to serve the resource can ask for it.
    """

    def __init__(
        self,
        fanout: MemberFanout,
        content: BundleContentReader,
        cache_hints: CacheHints,
        bridge: InputRequiredBridge,
    ) -> None:
        self._fanout = fanout
        self._content = content
        self._cache_hints = cache_hints
        self._bridge = bridge

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        uri = message.param("uri", "")
        if is_bundle_uri(uri):
            # the bundle's own scheme never falls through to a member
            return await self._bundle_resource(ctx, message, uri)
        # a member that disabled this resource in the bundle is never asked for it
        members = [
            server
            for server in self._fanout.members(ctx, ServerCapability.RESOURCES)
            if ctx.view.serves_member_entry(
                MemberEntryRef(kind=MemberEntryKind.RESOURCE, server_name=server.name, key=uri)
            )
        ]
        if ctx.era is ProtocolEra.STATELESS:
            return await self._bridge.serve(
                BridgedRead(
                    ctx=ctx,
                    message=message,
                    target=uri,
                    arguments={},
                    members=members,
                    read=lambda client, answers, upstream_state: client.session.read_resource(
                        uri,
                        input_responses=answers,
                        request_state=upstream_state,
                        allow_input_required=True,
                    ),
                    render=lambda result: self._shaped(ctx, dump(result)),
                    failed=lambda server, exc: self._not_found_error(ctx, uri),
                )
            )
        result = await self._fanout.first(
            ctx,
            lambda client: client.read_resource_mcp(uri),
            capability=ServerCapability.RESOURCES,
            among=members,
        )
        if result is None:
            return self._not_found(ctx, message, uri)
        return rpc_result(message.id, self._shaped(ctx, dump(result)))

    @staticmethod
    def _shaped(ctx: RequestContext, payload: dict[str, Any]) -> dict[str, Any]:
        return ctx.shape(payload, CacheHints.for_read(payload))

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
        hint = await self._cache_hints.for_bundle_resource()
        return rpc_result(message.id, ctx.shape(payload, hint))

    @staticmethod
    def _not_found_error(ctx: RequestContext, uri: str) -> dict[str, Any]:
        # -32002 for handshake clients, -32602 for modern ones.
        code = ctx.dialect.error_code(NeutralError.RESOURCE_NOT_FOUND)
        return {"code": code, "message": f"resource not found: {uri}", "data": {"uri": uri}}

    @classmethod
    def _not_found(cls, ctx: RequestContext, message: JsonRpcMessage, uri: str) -> Response:
        error = cls._not_found_error(ctx, uri)
        return rpc_error(message.id, error["code"], error["message"], data=error["data"])
