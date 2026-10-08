"""Holding back tool discovery until the servers it probes are committed."""

from uuid import UUID

from bundlemcp.application.contracts.upstream.tool_discovery import ToolDiscovery
from bundlemcp.application.schemas import DiscoveryResult


class ProbesAfterCommit:
    """Tool discovery whose background probes wait for the enclosing transaction.

    A probe runs in its own unit of work, so one scheduled inside a still-open
    transaction looks for a server that is not yet visible and finds nothing.
    This wrapper records each scheduled probe and hands it to the real
    discovery only when ``release`` is called after the commit; if the
    transaction fails, ``release`` is never reached and nothing is probed.
    """

    def __init__(self, discovery: ToolDiscovery) -> None:
        self._discovery = discovery
        self._held: list[UUID] = []

    async def schedule_probe(self, server_id: UUID) -> None:
        if server_id not in self._held:
            self._held.append(server_id)

    async def discover(self, server_id: UUID) -> DiscoveryResult:
        return await self._discovery.discover(server_id)

    async def release(self) -> None:
        """Schedule every held probe on the real discovery, in the order they were asked for."""
        held, self._held = self._held, []
        for server_id in held:
            await self._discovery.schedule_probe(server_id)
