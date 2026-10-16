"""Caching is a speed-up only: switching it off changes nothing else (SES-22)."""

import os
import pathlib
import subprocess
import sys

from bundlemcp.application.serving.runtime_config import RuntimeConfig
from bundlemcp.domain.config.config_entry import ConfigEntry
from bundlemcp.infrastructure.memory.in_memory_unit_of_work import InMemoryUnitOfWorkFactory

ROOT = pathlib.Path(__file__).resolve().parents[4]
RUNTIME_CONFIG_TESTS = [
    "packages/bundlemcp/tests/api/test_runtime_config.py",
    "packages/bundlemcp/tests/application/test_runtime_config_snapshot.py",
]


async def test_ses22_with_caching_off_a_change_needs_no_invalidation_event():
    """SES-22: the next read sees a stored change without any event announcing it."""
    units = InMemoryUnitOfWorkFactory()
    config = RuntimeConfig(units, cache_disabled=True)
    assert await config.get("call_timeout") == 60.0
    units.uow.config_entries.add(ConfigEntry(key="call_timeout", value=5.0))
    assert await config.get("call_timeout") == 5.0


def test_ses22_the_runtime_config_tests_pass_with_caching_off():
    """SES-22: the same tests, with BUNDLEMCP_CONFIG_CACHE_DISABLED set, pass unchanged."""
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *RUNTIME_CONFIG_TESTS],
        cwd=ROOT,
        env={**os.environ, "BUNDLEMCP_CONFIG_CACHE_DISABLED": "true"},
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert done.returncode == 0, done.stdout[-2000:]
