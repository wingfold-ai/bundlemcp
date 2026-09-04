from fastapi import Response

from bundlemcp.gateway.mcp_endpoint.jsonrpc_message import JsonRpcMessage
from bundlemcp.gateway.mcp_endpoint.session_context import SessionContext
from bundlemcp.gateway.signals import SignalBus


class CancelledNotificationHandler:
    """Route notifications/cancelled to whichever replica holds the in-flight call."""

    def __init__(self, signals: SignalBus) -> None:
        self._signals = signals

    async def handle(self, ctx: SessionContext, message: JsonRpcMessage) -> Response:
        # PROT-3
        request_id = message.params.get("requestId")
        if request_id is not None:
            await self._signals.cancel(ctx.session.session_id, str(request_id))
        return Response(status_code=202)
