import structlog
from fastapi import Response

from bundlemcp.gateway.mcp_endpoint.jsonrpc import rpc_result
from bundlemcp.gateway.mcp_endpoint.jsonrpc_message import JsonRpcMessage
from bundlemcp.gateway.mcp_endpoint.session_context import SessionContext

log = structlog.get_logger(__name__)


class ResourcesSubscribeHandler:
    """Accept the subscription request; the matching push depends on upstream pooling."""

    async def handle(self, ctx: SessionContext, message: JsonRpcMessage) -> Response:
        # notifications/resources/updated is pooling-dependent (ADR-0021) and is
        # not delivered between calls under per-call upstream connections.
        log.warning("resources.subscribe_push_pooling_dependent")
        return rpc_result(message.id, {})
