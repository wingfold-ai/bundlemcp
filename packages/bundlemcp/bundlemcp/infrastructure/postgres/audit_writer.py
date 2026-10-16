"""Audit writer: async relative to the response, bounded, never fails a call."""

import asyncio
import random
from collections.abc import Awaitable, Callable

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bundlemcp.application.contracts.observability.gateway_metrics import (
    AuditDropReason,
    GatewayMetrics,
)
from bundlemcp.domain.audit.audit_record import AuditRecord
from bundlemcp.infrastructure.postgres.rows.audit_record_row import AuditRecordRow

log = structlog.get_logger(__name__)

QUEUE_MAX = 1000
BATCH_MAX = 100
# a failed batch is retried this long before its records are given up
RETRY_SECONDS = 60.0
FIRST_BACKOFF = 0.5
MAX_BACKOFF = 8.0
# fits inside the gateway's graceful-shutdown window
DRAIN_DEADLINE_SECONDS = 10.0


def _named(record: AuditRecord) -> dict[str, str | None]:
    """What a loss is logged with, so a metering ledger can tell which invocation it was."""
    return {
        "idempotency_key": record.idempotency_key,
        "endpoint_name": record.endpoint_name,
        "presented_tool_name": record.presented_tool_name,
        "status": record.status.value,
    }


class QueuedAuditWriter:
    """Writes audit records in batches from a bounded in-process queue.

    ``record`` never blocks or raises. The drain loop writes up to
    ``BATCH_MAX`` records per transaction and retries a failed batch with
    backoff for ``RETRY_SECONDS`` before giving its records up. Every record
    that is never written (a full queue, a given-up write, the shutdown drain
    running out) is logged with its idempotency key and counted.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        metrics: GatewayMetrics,
        *,
        retry_seconds: float = RETRY_SECONDS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._sessions = session_factory
        self._metrics = metrics
        self._retry_seconds = retry_seconds
        self._sleep = sleep
        self._queue: asyncio.Queue[AuditRecord] = asyncio.Queue(maxsize=QUEUE_MAX)
        self._in_flight: list[AuditRecord] = []
        self._task: asyncio.Task | None = None
        self.dropped = 0  # records lost to a full queue since start

    async def start(self) -> None:
        self._task = asyncio.create_task(self._drain())

    async def stop(self, deadline: float = DRAIN_DEADLINE_SECONDS) -> None:
        """Drain the queue for up to ``deadline`` seconds, then name every record left."""
        if self._task is None:
            return
        try:
            async with asyncio.timeout(deadline):
                await self._queue.join()
        except TimeoutError:
            pass
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        lost = [*self._in_flight]
        while not self._queue.empty():
            lost.append(self._queue.get_nowait())
            self._queue.task_done()
        for record in lost:
            log.warning("audit.lost_on_shutdown", **_named(record))
            self._metrics.audit_dropped(reason=AuditDropReason.SHUTDOWN)
        self._in_flight = []

    @property
    def queue_depth(self) -> int:
        """Records waiting to be written, for the metrics' audit-queue gauge."""
        return self._queue.qsize()

    async def drain(self) -> None:
        """Wait until every queued record has been written."""
        await self._queue.join()

    def record(self, record: AuditRecord) -> None:
        """Fire-and-forget; never blocks or raises into the call path."""
        try:
            self._queue.put_nowait(record)
        except asyncio.QueueFull:
            self.dropped += 1
            log.warning("audit.queue_overflow", dropped=self.dropped, **_named(record))
            self._metrics.audit_dropped(reason=AuditDropReason.OVERFLOW)

    async def _drain(self) -> None:
        while True:
            batch = [await self._queue.get()]
            while len(batch) < BATCH_MAX and not self._queue.empty():
                batch.append(self._queue.get_nowait())
            self._in_flight = batch
            # cancelled mid-write (the shutdown drain ran out), the batch stays in
            # flight so stop() can name its records
            await self._write_with_retry(batch)
            self._in_flight = []
            for _ in batch:
                self._queue.task_done()

    async def _write_with_retry(self, batch: list[AuditRecord]) -> None:
        loop = asyncio.get_running_loop()
        give_up_at = loop.time() + self._retry_seconds
        backoff = FIRST_BACKOFF
        while True:
            try:
                async with self._sessions() as db:
                    db.add_all([AuditRecordRow(**record.model_dump()) for record in batch])
                    await db.commit()
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                if loop.time() + backoff > give_up_at:
                    for record in batch:
                        log.warning("audit.write_failed", **_named(record), exc_info=True)
                        self._metrics.audit_dropped(reason=AuditDropReason.WRITE_FAILED)
                    return
                log.info("audit.write_retrying", records=len(batch), backoff=backoff)
                await self._sleep(backoff * random.uniform(0.8, 1.2))
                backoff = min(backoff * 2, MAX_BACKOFF)
