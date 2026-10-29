"""The runtime-config snapshot that checks needing no I/O read (SEC-7)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from bundlemcp.application.serving.runtime_config import RuntimeConfig
from bundlemcp.domain.config.config_entry import ConfigEntry
from bundlemcp.domain.config.runtime_settings import MIB
from bundlemcp.infrastructure.memory.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
    InMemoryUnitOfWorkFactory,
)


class CountingUnits(InMemoryUnitOfWorkFactory):
    """Counts every unit of work opened."""

    def __init__(self) -> None:
        super().__init__()
        self.opened = 0

    @asynccontextmanager
    async def open(self) -> AsyncIterator[InMemoryUnitOfWork]:
        self.opened += 1
        yield self.uow


async def test_sec7_the_snapshot_never_opens_a_unit_of_work():
    """SEC-7: reading the request limit costs no database work, before or after a load."""
    units = CountingUnits()
    config = RuntimeConfig(units)
    assert config.snapshot.max_request_bytes == 4 * MIB
    assert units.opened == 0

    units.uow.config_entries.add(ConfigEntry(key="max_request_bytes", value=1 * MIB))
    await config.refresh()
    opened = units.opened
    for _ in range(3):
        assert config.snapshot.max_request_bytes == 1 * MIB
    assert units.opened == opened


async def test_sec7_a_flush_keeps_the_last_loaded_value():
    """SEC-7: between an invalidation and the reload the limit stays as stored, not the default."""
    units = CountingUnits()
    units.uow.config_entries.add(ConfigEntry(key="max_request_bytes", value=1 * MIB))
    config = RuntimeConfig(units)
    await config.refresh()
    await config.flush()
    assert config.snapshot.max_request_bytes == 1 * MIB
