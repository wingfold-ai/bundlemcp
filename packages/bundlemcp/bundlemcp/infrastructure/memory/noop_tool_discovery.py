from uuid import UUID

from bundlemcp.application.schemas import DiscoveryResult


class NoopToolDiscovery:
    """Discovery that never probes, for contexts with no upstream connectivity."""

    async def schedule_probe(self, server_id: UUID) -> None:
        return None

    async def discover(self, server_id: UUID) -> DiscoveryResult:
        return DiscoveryResult(error="discovery unavailable")
