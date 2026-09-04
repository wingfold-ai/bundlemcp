from fastapi import Response

from bundlemcp.gateway.mcp_endpoint.jsonrpc import rpc_result
from bundlemcp.gateway.mcp_endpoint.jsonrpc_message import JsonRpcMessage
from bundlemcp.gateway.mcp_endpoint.session_context import SessionContext


class LoggingSetLevelHandler:
    """Accepted; the level applies on each member's next connection."""

    async def handle(self, ctx: SessionContext, message: JsonRpcMessage) -> Response:
        # PROT-7: per-call model — no standing upstream connection to set it on now.
        return rpc_result(message.id, {})
