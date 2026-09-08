from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.repository import Repository
from bundlemcp.application.management.audit_filter import AuditFilter
from bundlemcp.domain.audit.audit_record import AuditRecord


@runtime_checkable
class AuditRepository(Repository[AuditRecord], Protocol):
    """The append-only record of tool calls."""

    async def page(
        self, filter_: AuditFilter, *, offset: int, limit: int
    ) -> tuple[int, list[AuditRecord]]:
        """One page of matching records, newest first, plus the total."""
        ...
