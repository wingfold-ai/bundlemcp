"""Moving queued log events into the shared live log buffer, off the request path."""

import asyncio

import structlog

from bundlemcp.application.contracts.live_state.live_log_buffer import LiveLogBuffer
from bundlemcp.infrastructure.config.live_log_handler import LiveLogHandler

log = structlog.get_logger(__name__)

BATCH_SIZE = 500
INTERVAL_SECONDS = 0.25


class LiveLogPublisher:
    """Drains the handler's queue in batches into the buffer, one pipeline per batch.

    A store outage costs only the live view: the batch is dropped, the failure
    is logged once until the store answers again, and the next batch is tried.
    Its own log lines never reach the queue.
    """

    def __init__(self, handler: LiveLogHandler, buffer: LiveLogBuffer) -> None:
        self._handler = handler
        self._buffer = buffer
        self._task: asyncio.Task[None] | None = None
        self._failing = False

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="live_log_publisher")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self.flush()  # what was logged before shutdown still reaches the view

    async def flush(self) -> None:
        """Publish everything queued now."""
        while batch := self._handler.drain(BATCH_SIZE):
            await self._publish(batch)

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(INTERVAL_SECONDS)
            await self.flush()

    async def _publish(self, batch: list) -> None:
        try:
            await self._buffer.append(batch)
        except Exception:
            if not self._failing:
                log.warning("live_log.publish_failed", dropped=len(batch))
            self._failing = True
            return
        if self._failing:
            log.info("live_log.publish_recovered")
        self._failing = False
