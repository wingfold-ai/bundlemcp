"""Deleting audit records older than the retention the operator chose."""

from datetime import timedelta

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWorkFactory
from bundlemcp.domain.shared.clock import Clock

# rows per transaction, so a large purge never holds the table in one long one
CHUNK_SIZE = 10_000


class AuditRetentionService:
    """Removes records past their retention, a chunk per transaction."""

    def __init__(self, units: UnitOfWorkFactory, clock: Clock) -> None:
        self._units = units
        self._clock = clock

    async def purge_older_than(self, days: int) -> int:
        """Delete every record older than ``days``; 0 keeps everything. How many went."""
        if days <= 0:
            return 0
        cutoff = self._clock.now() - timedelta(days=days)
        removed = 0
        while True:
            async with self._units.open() as uow:
                deleted = await uow.audit_records.delete_older_than(cutoff, limit=CHUNK_SIZE)
                await uow.commit()
            removed += deleted
            if deleted < CHUNK_SIZE:
                return removed
