"""Re-discovering a member whose list changed, once across every replica that heard it."""

from bundlemcp.application.contracts.live_state.refresh_lock import RefreshLock
from bundlemcp.application.contracts.persistence.invalidation_event import (
    EntityType,
    InvalidationEvent,
)
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWorkFactory
from bundlemcp.application.contracts.upstream.member_notification import (
    ListedKind,
    MemberListChanged,
)
from bundlemcp.application.discovery.discovery_service import DiscoveryService
from bundlemcp.domain.servers.mcp_server import McpServer

# one replica acts on a list change; the others, hearing the same change, stand down
REDISCOVER_KEY = "bmcp:rediscover:{server}:{list}"
REDISCOVER_GATE_SECONDS = 5

# which bundle content a member's prompt or resource list change alters
_MEMBER_LISTS: dict[ListedKind, EntityType] = {
    ListedKind.PROMPTS: "bundle_prompt",
    ListedKind.RESOURCES: "bundle_resource",
}


class MemberListChangeHandler:
    """Re-discovers a member whose list changed, so its bundles' clients list again.

    A tool list change re-discovers the server, whose bundle invalidation then
    tells clients to list again. A prompt or resource list change re-lists
    that list first, so clients that list again are served the new listing,
    and is announced even when the re-discovery fails, since the clients' live
    answers may differ. Several replicas hear the same change from their own
    sessions, so a short shared gate lets one of them act.
    """

    def __init__(
        self, units: UnitOfWorkFactory, discovery: DiscoveryService, gate: RefreshLock
    ) -> None:
        self._units = units
        self._discovery = discovery
        self._gate = gate

    async def handle(
        self, server: McpServer, notification: MemberListChanged, *, bound_to: str | None
    ) -> None:
        listed = notification.listed
        if not await self._claim(server, listed):
            return
        entity_type = _MEMBER_LISTS.get(listed)
        if entity_type is None:
            await self._discovery.discover(server.id, announce=True)
            return
        result = await self._discovery.discover(server.id, relisted=entity_type)
        if result.error is not None:
            await self._announce(server, entity_type)

    async def _claim(self, server: McpServer, listed: ListedKind) -> bool:
        key = REDISCOVER_KEY.format(server=server.name, list=listed.value)
        return await self._gate.acquire(key, ttl_seconds=REDISCOVER_GATE_SECONDS)

    async def _announce(self, server: McpServer, entity_type: EntityType) -> None:
        """Tell the clients of every bundle the server is an enabled member of."""
        async with self._units.open() as uow:
            for membership in await uow.memberships.for_server(server.id):
                if not membership.enabled:
                    continue
                bundle = await uow.bundles.get(membership.bundle_id)
                if bundle is not None:
                    uow.invalidate(
                        InvalidationEvent(
                            entity_type=entity_type, key=bundle.name, action="updated"
                        )
                    )
            await uow.commit()
