"""Re-reading every upstream server's tool list on a fixed interval for the life of the process."""

import asyncio

import structlog

from bundlemcp.application.contracts.live_state.refresh_lock import RefreshLock
from bundlemcp.application.discovery.discovery_service import DiscoveryService
from bundlemcp.application.schemas import DiscoverySweep

log = structlog.get_logger(__name__)

LEASE_KEY = "bundlemcp:discovery:sweep"


class ToolRefresher:
    """Every replica runs the loop; a lease in Valkey lets one of them sweep per interval.

    The lease is never released: it expires a little before the next tick, so it
    doubles as the rate limit across replicas. One failed sweep never ends the
    loop: the next interval retries.
    """

    def __init__(self, discovery: DiscoveryService, lease: RefreshLock, interval_seconds: int):
        self._discovery = discovery
        self._lease = lease
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None

    @property
    def _lease_seconds(self) -> int:
        # shorter than the interval, so the next tick on any replica finds it free
        return max(1, self._interval - max(1, self._interval // 10))

    async def refresh_once(self) -> DiscoverySweep | None:
        """Sweep every server, or return None when another replica holds this interval's lease."""
        if not await self._lease.acquire(LEASE_KEY, ttl_seconds=self._lease_seconds):
            return None
        return await self._discovery.discover_all()

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            try:
                sweep = await self.refresh_once()
                if sweep is not None:
                    log.info(
                        "discovery.swept",
                        servers=sweep.servers,
                        failed=sweep.failed,
                        changed=sweep.changed,
                    )
            except Exception:
                log.warning("discovery.sweep_failed", exc_info=True)
