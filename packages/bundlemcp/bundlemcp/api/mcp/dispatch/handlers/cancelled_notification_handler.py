from fastapi import Response

from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.application.contracts.live_state.signal_bus import SignalBus


class CancelledNotificationHandler:
    """Route notifications/cancelled to whichever replica holds the in-flight call.

    The call is found by the requester's call key and the request id it names,
    so a modern client cancels from a request of its own.
    """

    def __init__(self, signals: SignalBus) -> None:
        self._signals = signals

    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        request_id = message.params.get("requestId")
        if request_id is not None:
            await self._signals.cancel(ctx.call_key, str(request_id))
        return Response(status_code=202)
