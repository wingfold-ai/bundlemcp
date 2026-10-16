import asyncio
from typing import Any, Protocol, runtime_checkable

from bundlemcp.application.serving.call_handle import CallHandle
from bundlemcp.application.serving.stream_key import StreamKey

# Put on every open stream's queue when the replica shuts down, so the stream
# can end with a completion message instead of a dropped connection.
STREAM_CLOSING: Any = object()


@runtime_checkable
class StreamRegistry(Protocol):
    """This replica's open streams, in-flight calls, awaited replies and parked resumes."""

    def register_stream(self, key: StreamKey) -> asyncio.Queue: ...

    def unregister_stream(self, key: StreamKey, queue: asyncio.Queue) -> None: ...

    def deliver_local(self, stream_id: str, payload: dict[str, Any]) -> bool:
        """Put a message on a stream this replica holds; False when it holds none."""
        ...

    def broadcast_streams(self) -> list[StreamKey]:
        """Every stream this replica holds that receives list_changed notifications."""
        ...

    def close_streams(self) -> None:
        """End every open stream with a completion message."""
        ...

    def register_call(self, routing_key: str, request_id: str) -> CallHandle: ...

    def unregister_call(self, handle: CallHandle) -> None: ...

    def cancel_local(self, routing_key: str, request_id: str) -> bool:
        """Cancel a call this replica runs; False when it runs none by that id."""
        ...

    def cancel_calls(self) -> int:
        """Cancel every call this replica runs (shutdown); how many there were."""
        ...

    def register_reply(self, correlation_id: str) -> asyncio.Future: ...

    def unregister_reply(self, correlation_id: str) -> None: ...

    def reply_local(self, correlation_id: str, payload: dict[str, Any]) -> bool:
        """Resolve a reply future this replica awaits; False when it awaits none."""
        ...

    def register_resume(self, correlation_id: str) -> asyncio.Queue: ...

    def unregister_resume(self, correlation_id: str, queue: asyncio.Queue) -> None: ...

    def resume_local(self, correlation_id: str, phase: str, payload: dict[str, Any]) -> bool:
        """Feed a parked call this replica holds; False when it holds none."""
        ...
