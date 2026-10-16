import uuid
from typing import Protocol, runtime_checkable


@runtime_checkable
class FailureStreak(Protocol):
    """How many times in a row each upstream failed to connect, shared by every replica."""

    async def record_failure(self, server_id: uuid.UUID) -> int:
        """Count one more failure and return the streak including it."""
        ...

    async def reset(self, server_id: uuid.UUID) -> None:
        """End the streak: the upstream answered."""
        ...
