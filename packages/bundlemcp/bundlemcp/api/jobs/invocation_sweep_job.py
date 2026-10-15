"""Closing abandoned paused invocations on a fixed interval."""

import asyncio

import structlog

from bundlemcp.application.contracts.live_state.refresh_lock import RefreshLock
from bundlemcp.application.metering.invocation_sweeper import InvocationSweeper

log = structlog.get_logger(__name__)

LEASE_KEY = "bmcp:invocations:sweep"
INTERVAL_SECONDS = 30
TASK_NAME = "invocation_sweep"


class InvocationSweepJob:
    """Every replica runs the loop; a lease in Valkey lets one of them sweep per interval.

    An abandoned invocation is therefore closed at most one interval after
    its requestState expired. One failed sweep never ends the loop.
    """

    def __init__(
        self,
        sweeper: InvocationSweeper,
        lease: RefreshLock,
        interval_seconds: int = INTERVAL_SECONDS,
    ):
        self._sweeper = sweeper
        self._lease = lease
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None

    @property
    def _lease_seconds(self) -> int:
        # shorter than the interval, so the next tick on any replica finds it free
        return max(1, self._interval - max(1, self._interval // 10))

    async def sweep_once(self) -> int | None:
        """Sweep, or return None when another replica holds this interval's lease."""
        if not await self._lease.acquire(LEASE_KEY, ttl_seconds=self._lease_seconds):
            return None
        closed = await self._sweeper.sweep()
        if closed:
            log.info("metering.invocations_closed", closed=closed)
        return closed

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name=TASK_NAME)

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            try:
                await self.sweep_once()
            except Exception:
                log.warning("metering.invocation_sweep_failed", exc_info=True)
