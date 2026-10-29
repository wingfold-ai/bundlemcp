"""Moving stored secrets under the primary encryption key on a fixed interval."""

import asyncio

import structlog

from bundlemcp.application.contracts.live_state.refresh_lock import RefreshLock
from bundlemcp.application.upstream_oauth.reencryption_sweep import ReencryptionSweep
from bundlemcp.application.upstream_oauth.secret_reencryption import SecretReencryption

log = structlog.get_logger(__name__)

LEASE_KEY = "bundlemcp:token_encryption:sweep"
TASK_NAME = "token_encryption_sweep"


class SecretReencryptionJob:
    """Every replica runs the loop; a lease in Valkey lets one of them sweep per interval.

    A sweep covers upstream tokens, upstream client secrets and servers' static
    headers, and first encrypts static headers still stored in plaintext. Each
    sweep logs ``token_encryption.swept`` with its counts, ``sealed`` among them; once
    ``remaining_on_old_key`` is zero, no stored value needs an older key and the
    operator may drop it. One failed sweep never ends the loop.
    """

    def __init__(self, reencryption: SecretReencryption, lease: RefreshLock, interval_seconds: int):
        self._reencryption = reencryption
        self._lease = lease
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None

    @property
    def _lease_seconds(self) -> int:
        # shorter than the interval, so the next tick on any replica finds it free
        return max(1, self._interval - max(1, self._interval // 10))

    async def sweep_once(self) -> ReencryptionSweep | None:
        """Sweep, or return None when another replica holds this interval's lease."""
        if not await self._lease.acquire(LEASE_KEY, ttl_seconds=self._lease_seconds):
            return None
        sweep = await self._reencryption.sweep()
        log.info(
            "token_encryption.swept",
            rewritten=sweep.rewritten,
            remaining_on_old_key=sweep.remaining_on_old_key,
            undecryptable=sweep.undecryptable,
            sealed=sweep.sealed,
        )
        return sweep

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
                log.warning("token_encryption.sweep_failed", exc_info=True)
