import structlog
from fastapi import Response
from mcp.types import INVALID_PARAMS

from bundlemcp.api.mcp.dispatch.handlers.member_fanout import MemberFanout
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_error, rpc_result
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.application.contracts.live_state.resource_subscriptions import (
    ResourceSubscription,
)
from bundlemcp.domain.bundles.bundle_resource_uri import is_bundle_uri
from bundlemcp.domain.servers.server_capability import ServerCapability

log = structlog.get_logger(__name__)


class ResourcesSubscribeHandler:
    """Subscribe a handshake client to a member resource's updates.

    The subscription is relayed to every member that accepts subscriptions,
    on the upstream session bound to the client's session — the gateway does
    not know which member owns a URI until one answers for it — and recorded
    so an update reaches the client's stream from whichever replica hears it.
    A bundle's own resources change only through the gateway, which announces
    that as a list change.
    """

    def __init__(self, fanout: MemberFanout) -> None:
        self._fanout = fanout

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        uri = message.param("uri")
        if not isinstance(uri, str) or not uri:
            return rpc_error(message.id, INVALID_PARAMS, "resources/subscribe needs a uri")
        if ctx.session is None or is_bundle_uri(uri):
            return rpc_result(message.id, ctx.shape({}))
        subscriptions = self._fanout.leases.subscriptions
        for server in self._fanout.members(ctx, ServerCapability.RESOURCES):
            if not server.accepts_resource_subscriptions:
                continue
            try:
                async with self._fanout.lease(ctx, server, bound=True) as lease:
                    await lease.subscribe(uri)
            except Exception:
                log.info("resources.subscribe_refused", server=server.name, exc_info=True)
                continue
            await subscriptions.subscribe(
                ctx.session.session_id, ResourceSubscription(server_name=server.name, uri=uri)
            )
        return rpc_result(message.id, ctx.shape({}))
