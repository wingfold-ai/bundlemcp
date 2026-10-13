"""How a tool call's result reaches the client: one JSON body, or a stream ending in it."""

import asyncio
import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from fastapi import Response
from fastapi.responses import JSONResponse, StreamingResponse

from bundlemcp.api.mcp.protocol.sse import SSE_HEADERS, sse_data
from bundlemcp.api.mcp.relay import CallEvents

if TYPE_CHECKING:
    from bundlemcp.api.mcp.tool_call.tool_call import ToolCall

TERMINAL_PHASES = ("input_required", "result")


async def stream_events(
    queue: asyncio.Queue, rpc_id: Any, *, first: tuple[str, dict[str, Any]] | None = None
) -> AsyncIterator[str]:
    """Render a call's events as SSE until its result, or its request for input, arrives.

    Notifications pass through as they are; the terminal event carries the
    client's request id. A 'claimed' event only says a parked call took the
    retry's answers and is not shown to the client.
    """
    while True:
        phase, payload = first if first is not None else await queue.get()
        first = None
        if phase == "event":
            yield sse_data(payload)
        elif phase in TERMINAL_PHASES:
            yield sse_data({"jsonrpc": "2.0", "id": rpc_id, **payload})
            return


class BufferedCallResponse:
    """Wait for the upstream, then answer with the whole JSON-RPC message."""

    async def render(self, call: "ToolCall") -> Response:
        started = time.monotonic()
        outcome = await call.execute(None, None)
        await call.finish(outcome, started)
        return JSONResponse(outcome.jsonrpc(call.rpc_id, call.shape))


class StreamedCallResponse:
    # an input-required call outlives its own response stream
    """Stream the call's notifications as SSE events, then the final JSON-RPC message.

    Progress events are sent only when the client supplied a progress token; log
    messages whenever the upstream emits one the client asked for. The client
    closing the stream before the final event cancels the call, unless the call
    has asked the client for input, in which case it lives on until the client
    retries.
    """

    def __init__(self, progress_token: Any) -> None:
        # progress_token is None for a modern-era client that did not ask for
        # progress but is streamed anyway so that a disconnect is a cancellation
        self._progress_token = progress_token

    def _progress_event(self, progress: float, total: float | None, message: str | None) -> dict:
        params: dict[str, Any] = {"progressToken": self._progress_token, "progress": progress}
        if total is not None:
            params["total"] = total
        if message:
            params["message"] = message
        return {"jsonrpc": "2.0", "method": "notifications/progress", "params": params}

    async def render(self, call: "ToolCall") -> Response:
        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        events = CallEvents(call.correlation_id, queue, call.signals)
        call.attach(events)

        async def on_progress(progress: float, total: float | None, message: str | None) -> None:
            await events.emit("event", self._progress_event(progress, total, message))

        async def on_notification(payload: dict[str, Any]) -> None:
            await events.emit("event", payload)

        started = time.monotonic()
        task = call.detach(
            call.conclude(
                on_progress if self._progress_token is not None else None,
                on_notification,
                started,
            )
        )

        async def body():
            try:
                async for chunk in stream_events(queue, call.rpc_id):
                    yield chunk
            finally:
                if not task.done() and not events.parked:
                    call.disconnected()

        return StreamingResponse(body(), media_type="text/event-stream", headers=SSE_HEADERS)
