from datetime import datetime
from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.page_slice import PageSlice
from bundlemcp.application.contracts.persistence.repository import Repository
from bundlemcp.application.management.audit_cursor import AuditCursor
from bundlemcp.application.management.audit_filter import AuditFilter
from bundlemcp.domain.audit.audit_record import AuditRecord


@runtime_checkable
class AuditRepository(Repository[AuditRecord], Protocol):
    """The append-only record of tool calls."""

    async def page(
        self, filter_: AuditFilter, *, offset: int, limit: int
    ) -> PageSlice[AuditRecord]:
        """One page of matching records, newest first, plus the total."""
        ...

    async def page_after(
        self, filter_: AuditFilter, *, cursor: AuditCursor | None, limit: int
    ) -> list[AuditRecord]:
        """The next ``limit`` matching records, newest first, after ``cursor`` (None: the start).

        Keyed on the last record rather than an offset, so records written
        during a long walk neither repeat nor skip a row.
        """
        ...

    async def delete_older_than(self, cutoff: datetime, *, limit: int) -> int:
        """Delete up to ``limit`` records created before ``cutoff``; how many went."""
        ...
