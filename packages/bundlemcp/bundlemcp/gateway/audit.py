"""Audit writer (spec 50): async relative to the response, bounded, never fails a call."""

import asyncio

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bundlemcp.models import AuditRecord

log = structlog.get_logger(__name__)

QUEUE_MAX = 1000  # AUD-3: overflow is a metric/log event, not silent loss


class AuditWriter:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory
        self._queue: asyncio.Queue[AuditRecord] = asyncio.Queue(maxsize=QUEUE_MAX)
        self._task: asyncio.Task | None = None
        self.dropped = 0  # exported as a metric (OBS-2)

    async def start(self) -> None:
        self._task = asyncio.create_task(self._drain())

    async def stop(self) -> None:
        if self._task is not None:
            await self._queue.join()
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def record(self, record: AuditRecord) -> None:
        """AUD-3: fire-and-forget; never blocks or raises into the call path."""
        try:
            self._queue.put_nowait(record)
        except asyncio.QueueFull:
            self.dropped += 1
            log.warning("audit.queue_overflow", dropped=self.dropped)

    async def _drain(self) -> None:
        while True:
            record = await self._queue.get()
            try:
                async with self._sessions() as db:
                    db.add(record)
                    await db.commit()
            except Exception:
                log.warning("audit.write_failed", exc_info=True)
            finally:
                self._queue.task_done()
