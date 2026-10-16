import structlog
from fastapi import Response
from mcp.types import INVALID_PARAMS

from bundlemcp.api.mcp.dispatch.handlers.member_fanout import MemberFanout
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_error, rpc_result
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext

log = structlog.get_logger(__name__)


class ResourcesUnsubscribeHandler:
    """End a handshake client's subscription to a resource, upstream and in the record."""

    def __init__(self, fanout: MemberFanout) -> None:
        self._fanout = fanout

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        uri = message.param("uri")
        if not isinstance(uri, str) or not uri:
            return rpc_error(message.id, INVALID_PARAMS, "resources/unsubscribe needs a uri")
        if ctx.session is None:
            return rpc_result(message.id, ctx.shape({}))
        subscriptions = self._fanout.leases.subscriptions
        for subscription in await subscriptions.of_stream(ctx.session.session_id):
            if subscription.uri != uri:
                continue
            await subscriptions.unsubscribe(ctx.session.session_id, subscription)
            server = ctx.view.servers.get(subscription.server_name)
            if server is None:
                continue
            try:
                async with self._fanout.lease(ctx, server, bound=True) as lease:
                    await lease.unsubscribe(uri)
            except Exception:
                log.info("resources.unsubscribe_failed", server=server.name, exc_info=True)
        return rpc_result(message.id, ctx.shape({}))
