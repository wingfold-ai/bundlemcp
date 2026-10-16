from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.readiness_report import ReadinessReport


@runtime_checkable
class ReadinessProbe(Protocol):
    """Whether this replica's stores can be reached and its schema is current, right now."""

    async def check(self) -> ReadinessReport:
        """Run every check; a failing store is reported, never raised."""
        ...
