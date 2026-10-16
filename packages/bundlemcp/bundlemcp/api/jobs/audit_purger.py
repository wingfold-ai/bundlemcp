"""Applying the audit retention on a fixed interval."""

import asyncio

import structlog

from bundlemcp.application.contracts.live_state.refresh_lock import RefreshLock
from bundlemcp.application.management.audit_retention_service import AuditRetentionService
from bundlemcp.application.serving.runtime_config import RuntimeConfig

log = structlog.get_logger(__name__)

LEASE_KEY = "bmcp:audit:purge"
INTERVAL_SECONDS = 900
TASK_NAME = "audit_purge"


class AuditPurger:
    """Every replica runs the loop; a lease in Valkey lets one of them purge per interval.

    ``audit_retention_days`` is read on every run, so a change applies at the
    next one without a restart. One failed run never ends the loop.
    """

    def __init__(
        self,
        retention: AuditRetentionService,
        runtime_config: RuntimeConfig,
        lease: RefreshLock,
        interval_seconds: int = INTERVAL_SECONDS,
    ) -> None:
        self._retention = retention
        self._runtime_config = runtime_config
        self._lease = lease
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None

    @property
    def _lease_seconds(self) -> int:
        # shorter than the interval, so the next tick on any replica finds it free
        return max(1, self._interval - max(1, self._interval // 10))

    async def purge_once(self) -> int | None:
        """Purge, or return None when another replica holds this interval's lease."""
        if not await self._lease.acquire(LEASE_KEY, ttl_seconds=self._lease_seconds):
            return None
        days = int(await self._runtime_config.get("audit_retention_days"))
        removed = await self._retention.purge_older_than(days)
        if removed:
            log.info("audit.purged", removed=removed, retention_days=days)
        return removed

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
                await self.purge_once()
            except Exception:
                log.warning("audit.purge_failed", exc_info=True)
