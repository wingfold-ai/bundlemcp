"""The periodic re-encryption of stored secrets (DEP-9): one replica per interval."""

import asyncio

import pytest
from bundlemcp.api.jobs.secret_reencryption_job import TASK_NAME, SecretReencryptionJob
from bundlemcp.application.upstream_oauth.reencryption_sweep import ReencryptionSweep
from bundlemcp.infrastructure.valkey.refresh_lock import ValkeyRefreshLock
from cryptography.fernet import Fernet
from structlog.testing import capture_logs

from tests.conftest import hermetic_settings, serving


class CountingSweep:
    def __init__(self) -> None:
        self.sweeps = 0

    async def sweep(self) -> ReencryptionSweep:
        self.sweeps += 1
        return ReencryptionSweep(rewritten=2, remaining_on_old_key=0, undecryptable=1)


async def test_dep9_only_one_replica_sweeps_per_interval(redis):
    """DEP-9: a second replica finds the interval's lease held and skips its tick."""
    work = CountingSweep()
    first = SecretReencryptionJob(work, ValkeyRefreshLock(redis), interval_seconds=3600)
    second = SecretReencryptionJob(work, ValkeyRefreshLock(redis), interval_seconds=3600)
    assert await first.sweep_once() is not None
    assert await second.sweep_once() is None
    assert work.sweeps == 1


async def test_dep9_the_swept_event_carries_the_counts(redis):
    """DEP-9: the log says how many values still need an older key."""
    job = SecretReencryptionJob(CountingSweep(), ValkeyRefreshLock(redis), interval_seconds=3600)
    with capture_logs() as logs:
        await job.sweep_once()
    [event] = [e for e in logs if e["event"] == "token_encryption.swept"]
    assert (event["rewritten"], event["remaining_on_old_key"], event["undecryptable"]) == (2, 0, 1)


def _job_running() -> bool:
    return any(task.get_name() == TASK_NAME for task in asyncio.all_tasks())


@pytest.mark.parametrize(
    ("interval", "keys", "expected"),
    [(3600, True, True), (0, True, False), (3600, False, False)],
    ids=["keys-and-interval", "interval-zero", "no-keys"],
)
async def test_dep9_the_job_runs_only_with_keys_and_an_interval(
    engine, redis, interval, keys, expected
):
    """DEP-9: 0 disables the passes, and without encryption keys there is nothing to move."""
    settings = hermetic_settings(
        token_reencryption_interval=interval,
        token_encryption_keys=[Fernet.generate_key().decode()] if keys else [],
    )
    async with serving(engine, redis, settings=settings):
        assert _job_running() is expected
