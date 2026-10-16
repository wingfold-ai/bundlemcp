from typing import Protocol, runtime_checkable


@runtime_checkable
class StreamPresence(Protocol):
    """Which notification streams some replica holds right now, shared by every replica.

    A stream is held while its replica keeps refreshing it; one whose holder
    died stops being held within the hold's lifetime.
    """

    async def hold(self, stream_id: str) -> None:
        """Record or refresh that this replica holds the stream."""
        ...

    async def release(self, stream_id: str) -> None:
        """Drop this replica's hold; a hold another replica took over is left alone."""
        ...

    async def is_held(self, stream_id: str) -> bool:
        """Whether any replica holds the stream."""
        ...
