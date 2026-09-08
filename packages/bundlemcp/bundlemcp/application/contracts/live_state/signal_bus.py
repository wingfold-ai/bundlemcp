from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SignalBus(Protocol):
    """Reaches the replica that holds a client's stream, whichever replica that is."""

    async def cancel(self, routing_key: str, request_id: str) -> None:
        """Ask the holder of an in-flight call to cancel it."""
        ...

    async def deliver(self, stream_id: str, payload: dict[str, Any]) -> None:
        """Put a message on a client's open stream."""
        ...

    async def reply(self, correlation_id: str, payload: dict[str, Any]) -> None:
        """Route a client's answer to the call awaiting it."""
        ...

    async def resume(self, correlation_id: str, phase: str, payload: dict[str, Any]) -> None:
        """Feed a retry's answers to the parked call that asked for them."""
        ...
