"""Sweeping expired grants and tokens on a fixed interval for the life of the process."""

import asyncio

import structlog

from bundlemcp.services.oauth_server import TokenPurgeService
from bundlemcp.store import UnitOfWorkFactory

log = structlog.get_logger(__name__)

PURGE_INTERVAL_SECONDS = 600


class TokenPurger:
    """One failed sweep never ends the loop: the next interval retries."""

    def __init__(self, units: UnitOfWorkFactory, interval_seconds: float = PURGE_INTERVAL_SECONDS):
        self._units = units
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None

    async def purge_once(self) -> int:
        async with self._units.open() as uow:
            return await TokenPurgeService(uow).purge_expired()

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
                removed = await self.purge_once()
                if removed:
                    log.info("oauth.purged", removed=removed)
            except Exception:
                log.warning("oauth.purge_failed", exc_info=True)
