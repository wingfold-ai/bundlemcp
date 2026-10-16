from datetime import datetime

from bundlemcp.application.management.audit_cursor import AuditCursor
from bundlemcp.application.management.audit_filter import AuditFilter
from bundlemcp.domain.audit.audit_record import AuditRecord
from bundlemcp.infrastructure.memory.in_memory_repository import InMemoryRepository


class InMemoryAuditRepository(InMemoryRepository[AuditRecord]):
    async def page(
        self, filter_: AuditFilter, *, offset: int, limit: int
    ) -> tuple[int, list[AuditRecord]]:
        rows = self.where(lambda r: self._matches(r, filter_))
        ordered = sorted(rows, key=lambda r: (r.created_at, str(r.id)), reverse=True)
        return len(ordered), ordered[offset : offset + limit]

    async def page_after(
        self, filter_: AuditFilter, *, cursor: AuditCursor | None, limit: int
    ) -> list[AuditRecord]:
        rows = sorted(
            self.where(lambda r: self._matches(r, filter_)),
            key=lambda r: (r.created_at, r.id),
            reverse=True,
        )
        if cursor is not None:
            rows = [r for r in rows if (r.created_at, r.id) < (cursor.created_at, cursor.id)]
        return rows[:limit]

    async def delete_older_than(self, cutoff: datetime, *, limit: int) -> int:
        doomed = sorted(self.where(lambda r: r.created_at < cutoff), key=lambda r: r.created_at)
        for record in doomed[:limit]:
            await self.delete(record)
        return len(doomed[:limit])

    @staticmethod
    def _matches(record: AuditRecord, f: AuditFilter) -> bool:
        return (
            (f.created_from is None or record.created_at >= f.created_from)
            and (f.created_to is None or record.created_at <= f.created_to)
            and (f.kind is None or record.kind == f.kind)
            and (f.endpoint_name is None or record.endpoint_name == f.endpoint_name)
            and (f.bundle_name is None or record.bundle_name == f.bundle_name)
            and (f.server_name is None or record.server_name == f.server_name)
            and (
                f.tool_name is None
                or f.tool_name in (record.tool_name, record.presented_tool_name)
            )
            and (f.user_id is None or record.user_id == f.user_id)
            and (f.api_key_id is None or record.api_key_id == f.api_key_id)
            and (f.status is None or record.status == f.status)
            and (f.idempotency_key is None or record.idempotency_key == f.idempotency_key)
        )
