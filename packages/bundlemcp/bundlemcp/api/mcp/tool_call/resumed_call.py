"""A stateless client's retry for a call parked on some replica."""

# the resume half of park and resume.

import asyncio
from typing import Any

import structlog
from fastapi import Response
from fastapi.responses import StreamingResponse

from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.api.mcp.protocol.sse import SSE_HEADERS
from bundlemcp.api.mcp.relay import RequestState
from bundlemcp.api.mcp.tool_call.call_response import stream_events
from bundlemcp.api.mcp.tool_call.tool_call import ToolCall
from bundlemcp.api.mcp.tool_call.tool_call_support import ToolCallSupport
from bundlemcp.domain.bundles.presented_tool import PresentedTool

log = structlog.get_logger(__name__)


class ResumedCall:
    """Hand the client's answers to the parked call and stream what it says next.

    The answers go out as a reply signal under the call's correlation id; the
    replica holding the call resolves its wait and reports back through the
    same key. If no replica claims the answers within a short grace period the
    parked call is gone, and the call is re-run with the answers pre-loaded.
    """

    def __init__(
        self,
        support: ToolCallSupport,
        ctx: RequestContext,
        message: JsonRpcMessage,
        tool: PresentedTool,
        state: RequestState,
        responses: dict[str, Any],
    ) -> None:
        self._support = support
        self._ctx = ctx
        self._message = message
        self._tool = tool
        self._state = state
        self._responses = responses

    async def run(self) -> Response:
        registry = self._support.registry
        queue = registry.register_resume(self._state.correlation_id)
        await self._support.signals.reply(self._state.correlation_id, {"result": self._responses})
        try:
            first = await asyncio.wait_for(queue.get(), timeout=self._support.resume_grace)
        except TimeoutError:
            registry.unregister_resume(self._state.correlation_id, queue)
            # the parking replica is gone; re-run so the client still gets a result.
            log.warning("mrtr.park_lost", tool=self._state.target, sub=self._ctx.identity.sub)
            return await ToolCall(
                self._support,
                self._ctx,
                self._message,
                self._tool,
                preanswered=self._responses,
                idempotency_key=self._state.idempotency_key,
            ).run()

        async def body():
            try:
                async for chunk in stream_events(queue, self._message.id, first=first):
                    yield chunk
            finally:
                registry.unregister_resume(self._state.correlation_id, queue)

        return StreamingResponse(body(), media_type="text/event-stream", headers=SSE_HEADERS)
