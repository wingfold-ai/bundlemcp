from typing import Protocol, runtime_checkable
from uuid import UUID

from bundlemcp.application.schemas import DiscoveryResult


@runtime_checkable
class ToolDiscovery(Protocol):
    """Probing an upstream server for its tools, as the server service needs it."""

    async def schedule_probe(self, server_id: UUID) -> None:
        """Probe in the background; the caller never waits for the result."""
        ...

    async def discover(self, server_id: UUID, *, prune: bool = False) -> DiscoveryResult:
        """Probe now and report what was seen.

        ``prune`` deletes the server's stale tools, and their curation in every
        bundle, once the probe has succeeded; a failed probe deletes nothing.
        """
        ...
