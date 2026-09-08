from typing import Protocol, runtime_checkable


@runtime_checkable
class RefreshLock(Protocol):
    """A short-lived lock shared by every replica, so one refresh runs per connection."""

    async def acquire(self, key: str, *, ttl_seconds: int) -> bool:
        """Take the lock if nobody holds it; False when another holder has it."""
        ...

    async def release(self, key: str) -> None: ...
