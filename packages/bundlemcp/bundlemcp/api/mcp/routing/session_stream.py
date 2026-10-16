"""The server->client event stream of a session-era MCP connection (SSE)."""

import asyncio
from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse

from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.api.mcp.protocol.sse import (
    KEEPALIVE_SECONDS,
    SSE_HEADERS,
    SSE_KEEPALIVE,
    sse_data,
)
from bundlemcp.application.contracts.live_state.session_store import SessionStore
from bundlemcp.application.contracts.live_state.stream_presence import StreamPresence
from bundlemcp.application.contracts.live_state.stream_registry import (
    STREAM_CLOSING,
    StreamRegistry,
)
from bundlemcp.application.serving.runtime_config import RuntimeConfig
from bundlemcp.application.serving.stream_key import StreamKey


class SessionStream:
    """Owns the SSE event stream for a session."""

    def __init__(
        self,
        registry: StreamRegistry,
        sessions: SessionStore,
        runtime_config: RuntimeConfig,
        presence: StreamPresence,
    ) -> None:
        self._registry = registry
        self._sessions = sessions
        self._runtime_config = runtime_config
        self._presence = presence

    def open(self, ctx: RequestContext) -> StreamingResponse:
        key = StreamKey(
            endpoint_name=ctx.view.endpoint.name,
            bundle_name=ctx.view.bundle.name,
            stream_id=ctx.routing_key,
        )
        queue = self._registry.register_stream(key)
        return StreamingResponse(
            self._events(key, queue),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    async def _events(self, key: StreamKey, queue: asyncio.Queue) -> AsyncIterator[str]:
        try:
            await self._presence.hold(key.stream_id)
            yield ": connected\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
                except TimeoutError:
                    yield SSE_KEEPALIVE
                    await self._presence.hold(key.stream_id)
                    lifetime = await self._runtime_config.session_lifetime()
                    await self._sessions.touch(key.stream_id, lifetime)  # stream open = active
                    continue
                if payload is STREAM_CLOSING:
                    return
                yield sse_data(payload)
        finally:
            self._registry.unregister_stream(key, queue)
            await self._presence.release(key.stream_id)
