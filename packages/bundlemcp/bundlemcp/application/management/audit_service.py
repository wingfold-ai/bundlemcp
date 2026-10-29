"""Read access to the append-only audit log with the standard list filters."""

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.management.audit_filter import AuditFilter
from bundlemcp.application.schemas import AuditRecordRead, Page

__all__ = ["AuditFilter", "AuditService"]


class AuditService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._records = uow.audit_records

    async def list(self, filter_: AuditFilter, *, offset: int, limit: int) -> Page[AuditRecordRead]:
        page_slice = await self._records.page(filter_, offset=offset, limit=limit)
        return Page.of(page_slice, offset=offset, limit=limit, read=AuditRecordRead.from_entity)
