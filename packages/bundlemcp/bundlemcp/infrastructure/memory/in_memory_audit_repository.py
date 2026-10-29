from datetime import datetime

from bundlemcp.application.management.audit_cursor import AuditCursor
from bundlemcp.application.management.audit_filter import AuditFilter
from bundlemcp.domain.audit.audit_record import AuditRecord
from bundlemcp.infrastructure.memory.in_memory_repository import InMemoryRepository


class InMemoryAuditRepository(InMemoryRepository[AuditRecord]):
    async def page(
        self, filter_: AuditFilter, *, offset: int, limit: int
    ) -> tuple[int, list[AuditRecord]]:
        ordered = self._newest_first(filter_)
        return len(ordered), ordered[offset : offset + limit]

    async def page_after(
        self, filter_: AuditFilter, *, cursor: AuditCursor | None, limit: int
    ) -> list[AuditRecord]:
        rows = self._newest_first(filter_)
        if cursor is not None:
            rows = [r for r in rows if (r.created_at, r.id) < (cursor.created_at, cursor.id)]
        return rows[:limit]

    async def delete_older_than(self, cutoff: datetime, *, limit: int) -> int:
        doomed = sorted(self.where(lambda r: r.created_at < cutoff), key=lambda r: r.created_at)
        for record in doomed[:limit]:
            await self.delete(record)
        return len(doomed[:limit])

    def _newest_first(self, filter_: AuditFilter) -> list[AuditRecord]:
        return sorted(self.where(filter_.matches), key=lambda r: (r.created_at, r.id), reverse=True)
