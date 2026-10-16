import asyncio

from bundlemcp.application.contracts.live_state.live_log_entry import LiveLogEntry


class InMemoryLiveLogBuffer:
    """The live log buffer for tests: a capped list with sequential ids."""

    def __init__(self, cap: int = 10_000) -> None:
        self.entries: list[LiveLogEntry] = []
        self._cap = cap
        self._next = 0
        self._added = asyncio.Event()

    async def append(self, entries: list[LiveLogEntry]) -> None:
        for entry in entries:
            self._next += 1
            self.entries.append(entry.model_copy(update={"id": f"{self._next}-0"}))
        del self.entries[: max(0, len(self.entries) - self._cap)]
        self._added.set()

    async def latest(self, limit: int) -> list[LiveLogEntry]:
        return self.entries[-limit:]

    async def after(self, cursor: str, *, limit: int, wait_seconds: float) -> list[LiveLogEntry]:
        floor = self._next if cursor == "$" else int(cursor.split("-")[0])
        newer = [e for e in self.entries if int(e.id.split("-")[0]) > floor]
        if not newer:
            self._added.clear()
            try:
                await asyncio.wait_for(self._added.wait(), wait_seconds)
            except TimeoutError:
                return []
            newer = [e for e in self.entries if int(e.id.split("-")[0]) > floor]
        return newer[:limit]
