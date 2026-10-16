"""The whole filtered audit log, record by record, for an export."""

from collections.abc import AsyncIterator

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWorkFactory
from bundlemcp.application.management.audit_cursor import AuditCursor
from bundlemcp.application.management.audit_filter import AuditFilter
from bundlemcp.application.schemas import AuditRecordRead

PAGE_SIZE = 500


class AuditExportService:
    """Walks every matching record newest first, a page per short transaction.

    No transaction stays open while the export is sent, and memory stays one
    page deep however large the result.
    """

    def __init__(self, units: UnitOfWorkFactory) -> None:
        self._units = units

    async def records(self, filter_: AuditFilter) -> AsyncIterator[AuditRecordRead]:
        cursor: AuditCursor | None = None
        while True:
            async with self._units.open() as uow:
                page = await uow.audit_records.page_after(filter_, cursor=cursor, limit=PAGE_SIZE)
            for record in page:
                yield AuditRecordRead.from_entity(record)
            if len(page) < PAGE_SIZE:
                return
            cursor = AuditCursor(created_at=page[-1].created_at, id=page[-1].id)
