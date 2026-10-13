"""Audit writer: async relative to the response, bounded, never fails a call."""

import asyncio

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bundlemcp.domain.audit.audit_record import AuditRecord
from bundlemcp.infrastructure.postgres.rows.audit_record_row import AuditRecordRow

log = structlog.get_logger(__name__)

QUEUE_MAX = 1000  # overflow is logged with a dropped count, never silent


class QueuedAuditWriter:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory
        self._queue: asyncio.Queue[AuditRecord] = asyncio.Queue(maxsize=QUEUE_MAX)
        self._task: asyncio.Task | None = None
        self.dropped = 0  # logged on overflow; not exported as a metric yet

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

    async def drain(self) -> None:
        """Wait until every queued record has been written."""
        await self._queue.join()

    def record(self, record: AuditRecord) -> None:
        """Fire-and-forget; never blocks or raises into the call path."""
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
                    db.add(AuditRecordRow(**record.model_dump()))
                    await db.commit()
            except Exception:
                log.warning("audit.write_failed", exc_info=True)
            finally:
                self._queue.task_done()
