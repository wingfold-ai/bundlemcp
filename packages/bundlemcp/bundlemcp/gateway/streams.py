"""Per-replica registries for live streams and in-flight calls.

These hold the ONLY replica-pinned objects the architecture permits: open
HTTP streams and the asyncio primitives attached to them. Everything else
stays in Redis; cross-replica messages reach these objects via the SignalBus.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CallHandle:
    """An in-flight tools/call on this replica (the target for cancellation)."""

    session_id: str
    request_id: str
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    progress_queue: asyncio.Queue = field(default_factory=asyncio.Queue)  # PROT-1


class StreamRegistry:
    def __init__(self) -> None:
        self._streams: dict[str, asyncio.Queue] = {}  # session_id -> GET stream queue
        self._calls: dict[tuple[str, str], CallHandle] = {}
        self._replies: dict[str, asyncio.Future] = {}  # correlation_id -> reply future

    # --- GET event streams (EP-1a) ---

    def register_stream(self, session_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._streams[session_id] = queue
        return queue

    def unregister_stream(self, session_id: str, queue: asyncio.Queue) -> None:
        if self._streams.get(session_id) is queue:
            del self._streams[session_id]

    def deliver_local(self, session_id: str, payload: dict[str, Any]) -> bool:
        queue = self._streams.get(session_id)
        if queue is None:
            return False
        queue.put_nowait(payload)
        return True

    def broadcast_sessions(self) -> list[str]:
        return list(self._streams)

    # --- in-flight calls (PROT-3) ---

    def register_call(self, session_id: str, request_id: str) -> CallHandle:
        handle = CallHandle(session_id=session_id, request_id=request_id)
        self._calls[(session_id, request_id)] = handle
        return handle

    def unregister_call(self, handle: CallHandle) -> None:
        self._calls.pop((handle.session_id, handle.request_id), None)

    def cancel_local(self, session_id: str, request_id: str) -> bool:
        handle = self._calls.get((session_id, request_id))
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
