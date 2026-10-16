from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.live_state.live_log_entry import LiveLogEntry


@runtime_checkable
class LiveLogBuffer(Protocol):
    """The newest log events of every replica, in one capped, ephemeral buffer."""

    async def append(self, entries: list[LiveLogEntry]) -> None:
        """Store entries in order; the oldest beyond the cap are dropped."""
        ...

    async def latest(self, limit: int) -> list[LiveLogEntry]:
        """Up to ``limit`` of the newest entries, oldest first."""
        ...

    async def after(self, cursor: str, *, limit: int, wait_seconds: float) -> list[LiveLogEntry]:
        """Entries stored after ``cursor``, oldest first, waiting up to ``wait_seconds`` for one.

        ``cursor`` is an entry id, or ``"$"`` for only entries stored from now on.
        """
        ...
