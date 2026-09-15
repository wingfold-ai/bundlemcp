import structlog
from fastapi import Response

from bundlemcp.api.mcp.protocol.jsonrpc import rpc_result
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext

log = structlog.get_logger(__name__)


class ResourcesSubscribeHandler:
    """Accept the subscription request; the matching push depends on upstream pooling."""

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        # notifications/resources/updated is pooling-dependent (ADR-0021) and is
        # not delivered between calls under per-call upstream connections.
        log.warning("resources.subscribe_push_pooling_dependent")
        return rpc_result(message.id, ctx.shape({}))
