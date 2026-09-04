"""How a tool call's result reaches the client: one JSON body, or a stream ending in it."""

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any

from fastapi import Response
from fastapi.responses import JSONResponse, StreamingResponse

from bundlemcp.gateway.mcp_endpoint.tool_call.call_outcome import CallOutcome

if TYPE_CHECKING:
    from bundlemcp.gateway.mcp_endpoint.tool_call.tool_call import ToolCall

SSE_HEADERS = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}


class BufferedCallResponse:
    """Wait for the upstream, then answer with the whole JSON-RPC message."""

    async def render(self, call: "ToolCall") -> Response:
        started = time.monotonic()
        outcome = await call.execute(None)
        await call.finish(outcome, started)
        return JSONResponse(outcome.jsonrpc(call.rpc_id))


class StreamedCallResponse:
    """Stream notifications/progress as SSE events, then the final JSON-RPC message."""

    def __init__(self, progress_token: Any) -> None:
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
            await queue.put(("progress", self._progress_event(progress, total, message)))

        async def runner() -> None:
            await queue.put(("final", await call.execute(on_progress)))

        async def events():
            started = time.monotonic()
            task = asyncio.create_task(runner())
            try:
                while True:
                    kind, data = await queue.get()
                    if kind == "progress":
                        yield f"data: {json.dumps(data)}\n\n"
                        continue
                    outcome: CallOutcome = data
                    await call.finish(outcome, started)
                    yield f"data: {json.dumps(outcome.jsonrpc(call.rpc_id))}\n\n"
                    return
            finally:
                if not task.done():
                    task.cancel()

        return StreamingResponse(events(), media_type="text/event-stream", headers=SSE_HEADERS)
