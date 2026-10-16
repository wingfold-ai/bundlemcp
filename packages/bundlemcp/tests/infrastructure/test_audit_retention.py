"""Audit records past their retention are purged, on one replica per interval (OPS-5)."""

from datetime import UTC, datetime, timedelta

from bundlemcp.api.jobs.audit_purger import AuditPurger
from bundlemcp.application.management.audit_filter import AuditFilter
from bundlemcp.application.management.audit_retention_service import AuditRetentionService
from bundlemcp.application.serving.runtime_config import RuntimeConfig
from bundlemcp.domain.audit.audit_record import AuditRecord
from bundlemcp.domain.audit.audit_status import AuditStatus
from bundlemcp.domain.config.config_entry import ConfigEntry
from bundlemcp.infrastructure.memory.manual_clock import ManualClock
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWorkFactory
from bundlemcp.infrastructure.valkey.refresh_lock import ValkeyRefreshLock

NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)


def _record(age_days: int) -> AuditRecord:
    return AuditRecord(
        created_at=NOW - timedelta(days=age_days),
        endpoint_name="main",
        bundle_name="demo",
        status=AuditStatus.SUCCESS,
    )


async def _seeded(engine, redis, *ages: int) -> SqlAlchemyUnitOfWorkFactory:
    units = SqlAlchemyUnitOfWorkFactory(session_factory(engine), redis)
    async with units.open() as uow:
        for age in ages:
            uow.audit_records.add(_record(age))
        await uow.commit()
    return units


async def _ages(units) -> list[int]:
    async with units.open() as uow:
        _total, rows = await uow.audit_records.page(AuditFilter(), offset=0, limit=100)
    return sorted((NOW - row.created_at).days for row in rows)


async def _set_retention(units, days: int) -> None:
    async with units.open() as uow:
        existing = await uow.config_entries.get("audit_retention_days")
        if existing is not None:
            existing.value = days
            uow.config_entries.add(existing)
        else:
            uow.config_entries.add(ConfigEntry(key="audit_retention_days", value=days))
        await uow.commit()


async def test_ops5_old_records_purged(engine, redis):
    """OPS-5: with 30 days of retention a 40-day-old record goes and a 10-day-old one stays."""
    units = await _seeded(engine, redis, 10, 40)
    removed = await AuditRetentionService(units, ManualClock(NOW)).purge_older_than(30)
    assert removed == 1
    assert await _ages(units) == [10]


async def test_ops5_zero_keeps_everything(engine, redis):
    units = await _seeded(engine, redis, 10, 400)
    assert await AuditRetentionService(units, ManualClock(NOW)).purge_older_than(0) == 0
    assert await _ages(units) == [10, 400]


async def test_ops5_large_purges_go_in_chunks(engine, redis, monkeypatch):
    """OPS-5: a purge deletes chunk by chunk until nothing old is left."""
    monkeypatch.setattr("bundlemcp.application.management.audit_retention_service.CHUNK_SIZE", 2)
    units = await _seeded(engine, redis, 50, 51, 52, 53, 54, 1)
    assert await AuditRetentionService(units, ManualClock(NOW)).purge_older_than(30) == 5
    assert await _ages(units) == [1]


async def test_ops5_retention_change_applies_without_restart(engine, redis):
    """OPS-5: the job reads audit_retention_days on every run."""
    units = await _seeded(engine, redis, 10, 40)
    config = RuntimeConfig(units)
    purger = AuditPurger(
        AuditRetentionService(units, ManualClock(NOW)), config, ValkeyRefreshLock(redis), 60
    )
    assert await purger.purge_once() == 0  # the default 90 days
    await _set_retention(units, 7)
    await config.flush()  # what the invalidation event does on every replica
    await redis.delete("bmcp:audit:purge")  # the next interval
    assert await purger.purge_once() == 2
    assert await _ages(units) == []


async def test_ops5_one_replica_purges_per_interval(engine, redis):
    """OPS-5: two replicas reach the same tick; the lease lets one of them purge."""
    units = await _seeded(engine, redis, 400)

    def replica() -> AuditPurger:
        return AuditPurger(
            AuditRetentionService(units, ManualClock(NOW)),
            RuntimeConfig(units),
            ValkeyRefreshLock(redis),
        )

    assert [await replica().purge_once(), await replica().purge_once()] == [1, None]
