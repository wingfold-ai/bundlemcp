"""Reading the live log: the recent entries, then new ones as they arrive."""

from collections.abc import AsyncIterator

from bundlemcp.application.contracts.live_state.live_log_buffer import LiveLogBuffer
from bundlemcp.application.contracts.live_state.live_log_entry import LiveLogEntry
from bundlemcp.application.management.live_log_filter import LiveLogFilter

# how far back a filtered backfill looks; the buffer holds about ten thousand entries
BACKFILL_SCAN = 2_000
FOLLOW_BATCH = 200


class LiveLogService:
    """Serves the shared live log buffer, filtered on the gateway rather than in the browser."""

    def __init__(self, buffer: LiveLogBuffer) -> None:
        self._buffer = buffer

    async def recent(self, wanted: LiveLogFilter, *, limit: int) -> list[LiveLogEntry]:
        """Up to ``limit`` of the newest matching entries, oldest first."""
        entries = await self._buffer.latest(BACKFILL_SCAN)
        return [entry for entry in entries if wanted.matches(entry)][-limit:]

    async def follow(
        self, wanted: LiveLogFilter, *, after: str, wait_seconds: float
    ) -> AsyncIterator[list[LiveLogEntry]]:
        """Batches of matching entries stored after ``after``, forever; an empty batch is a pause.

        ``after`` is the last entry id the viewer saw, or ``"$"`` for new entries
        only. Resuming from an id continues without gaps or duplicates while that
        entry is still in the buffer.
        """
        cursor = after
        while True:
            entries = await self._buffer.after(
                cursor, limit=FOLLOW_BATCH, wait_seconds=wait_seconds
            )
            if entries:
                cursor = entries[-1].id
            yield [entry for entry in entries if wanted.matches(entry)]
