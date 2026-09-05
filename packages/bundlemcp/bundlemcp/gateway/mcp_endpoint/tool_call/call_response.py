"""How a tool call's result reaches the client: one JSON body, or a stream ending in it."""

import asyncio
import time
from typing import TYPE_CHECKING, Any

from fastapi import Response
from fastapi.responses import JSONResponse, StreamingResponse

from bundlemcp.gateway.mcp_endpoint.sse import SSE_HEADERS, sse_data
from bundlemcp.gateway.mcp_endpoint.tool_call.call_outcome import CallOutcome

if TYPE_CHECKING:
    from bundlemcp.gateway.mcp_endpoint.tool_call.tool_call import ToolCall


class BufferedCallResponse:
    """Wait for the upstream, then answer with the whole JSON-RPC message."""

    async def render(self, call: "ToolCall") -> Response:
        started = time.monotonic()
        outcome = await call.execute(None, None)
        await call.finish(outcome, started)
        return JSONResponse(outcome.jsonrpc(call.rpc_id, call.shape))


class StreamedCallResponse:
    """Stream the call's notifications as SSE events, then the final JSON-RPC message.

    Progress events are sent only when the client supplied a progress token; log
    messages whenever the upstream emits one the client asked for. The client
    closing the stream before the final event cancels the call.
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

        async def on_progress(progress: float, total: float | None, message: str | None) -> None:
            await queue.put(("event", self._progress_event(progress, total, message)))

        async def on_notification(payload: dict[str, Any]) -> None:
            await queue.put(("event", payload))

        async def runner() -> CallOutcome:
            outcome = await call.execute(
                on_progress if self._progress_token is not None else None, on_notification
            )
            await queue.put(("final", outcome))
            return outcome

        async def events():
            started = time.monotonic()
            task = asyncio.create_task(runner())
            try:
                while True:
                    kind, data = await queue.get()
                    if kind == "event":
                        yield sse_data(data)
                        continue
                    outcome: CallOutcome = data
                    await call.finish(outcome, started)
                    yield sse_data(outcome.jsonrpc(call.rpc_id, call.shape))
                    return
            finally:
                if not task.done():
                    call.disconnected(task, started)  # PROT-19

        return StreamingResponse(events(), media_type="text/event-stream", headers=SSE_HEADERS)
