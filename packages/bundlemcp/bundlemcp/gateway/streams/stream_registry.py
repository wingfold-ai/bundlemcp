import asyncio
from typing import Any

from bundlemcp.gateway.streams.call_handle import CallHandle
from bundlemcp.gateway.streams.stream_key import StreamKey

# Put on every open stream's queue when the replica shuts down, so the stream
# can end with a completion message instead of a dropped connection.
STREAM_CLOSING: Any = object()


class StreamRegistry:
    def __init__(self) -> None:
        self._streams: dict[str, tuple[StreamKey, asyncio.Queue]] = {}
        self._calls: dict[tuple[str, str], CallHandle] = {}
        self._replies: dict[str, asyncio.Future] = {}  # correlation_id -> reply future

    # --- notification streams: a handshake GET stream or a subscriptions/listen stream ---

    def register_stream(self, key: StreamKey) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._streams[key.stream_id] = (key, queue)
        return queue

    def unregister_stream(self, key: StreamKey, queue: asyncio.Queue) -> None:
        held = self._streams.get(key.stream_id)
        if held is not None and held[1] is queue:
            del self._streams[key.stream_id]

    def deliver_local(self, stream_id: str, payload: dict[str, Any]) -> bool:
        held = self._streams.get(stream_id)
        if held is None:
            return False
        held[1].put_nowait(payload)
        return True

    def broadcast_streams(self) -> list[StreamKey]:
        return [key for key, _queue in self._streams.values()]

    def close_streams(self) -> None:
        """Tell every open stream to end gracefully (replica shutdown)."""
        for _key, queue in self._streams.values():
            queue.put_nowait(STREAM_CLOSING)

    # --- in-flight calls (PROT-3) ---

    def register_call(self, routing_key: str, request_id: str) -> CallHandle:
        handle = CallHandle(routing_key=routing_key, request_id=request_id)
        self._calls[(routing_key, request_id)] = handle
        return handle

    def unregister_call(self, handle: CallHandle) -> None:
        self._calls.pop((handle.routing_key, handle.request_id), None)

    def cancel_local(self, routing_key: str, request_id: str) -> bool:
        handle = self._calls.get((routing_key, request_id))
        if handle is None:
            return False
        handle.cancel_event.set()
        return True

    # --- correlation replies (PROT-4) ---

    def register_reply(self, correlation_id: str) -> asyncio.Future:
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._replies[correlation_id] = future
        return future

    def unregister_reply(self, correlation_id: str) -> None:
        self._replies.pop(correlation_id, None)

    def reply_local(self, correlation_id: str, payload: dict[str, Any]) -> bool:
        future = self._replies.get(correlation_id)
        if future is None or future.done():
            return False
        future.set_result(payload)
        return True
