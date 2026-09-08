from typing import Protocol, runtime_checkable

from bundlemcp.domain.audit.audit_record import AuditRecord


@runtime_checkable
class AuditSink(Protocol):
    """Where a finished tool call's record goes; never slows or fails the call."""

    def record(self, record: AuditRecord) -> None:
        """Accept a record for writing; fire-and-forget."""
        ...

    async def drain(self) -> None:
        """Wait until every accepted record has been written."""
        ...
