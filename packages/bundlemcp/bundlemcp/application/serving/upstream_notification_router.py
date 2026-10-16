"""Acting on what a member says outside any request: list changes, resource updates, logs."""

from typing import Any

import structlog

from bundlemcp.application.contracts.live_state.refresh_lock import RefreshLock
from bundlemcp.application.contracts.live_state.resource_subscriptions import (
    ResourceSubscription,
    ResourceSubscriptions,
)
from bundlemcp.application.contracts.live_state.session_store import SessionStore
from bundlemcp.application.contracts.live_state.signal_bus import SignalBus
from bundlemcp.application.contracts.persistence.invalidation_event import (
    EntityType,
    InvalidationEvent,
)
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWorkFactory
from bundlemcp.application.discovery.discovery_service import DiscoveryService
from bundlemcp.application.serving.list_changed_notifier import (
    PROMPTS_LIST_CHANGED,
    RESOURCES_LIST_CHANGED,
    TOOLS_LIST_CHANGED,
)
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.sessions.log_levels import LOG_LEVELS, at_least

log = structlog.get_logger(__name__)

RESOURCE_UPDATED = "notifications/resources/updated"
LOG_MESSAGE = "notifications/message"
# one replica acts on a list change; the others, hearing the same change, stand down
REDISCOVER_KEY = "bmcp:rediscover:{server}:{list}"
REDISCOVER_GATE_SECONDS = 5

# which bundle content a member's prompt or resource list change alters
_MEMBER_LISTS: dict[str, EntityType] = {
    PROMPTS_LIST_CHANGED: "bundle_prompt",
    RESOURCES_LIST_CHANGED: "bundle_resource",
}


class UpstreamNotificationRouter:
    """Takes a member's notification to whoever it concerns, on whichever replica they are.

    A tool list change re-discovers the server, whose bundle invalidation then
    tells clients to list again; a prompt or resource list change is announced
    to the server's bundles directly. Several replicas hear the same change
    from their own sessions, so a short shared gate lets one of them act. A
    resource update goes to every stream subscribed to that resource, and a
    log message on an upstream session dedicated to a client's session goes
    to that client, at or above the level it asked for.
    """

    def __init__(
        self,
        units: UnitOfWorkFactory,
        discovery: DiscoveryService,
        gate: RefreshLock,
        subscriptions: ResourceSubscriptions,
        sessions: SessionStore,
        signals: SignalBus,
    ) -> None:
        self._units = units
        self._discovery = discovery
        self._gate = gate
        self._subscriptions = subscriptions
        self._sessions = sessions
        self._signals = signals

    async def received(
        self, server: McpServer, notification: dict[str, Any], *, bound_to: str | None
    ) -> None:
        method = notification.get("method")
        if method == TOOLS_LIST_CHANGED:
            if await self._claim(server, "tools"):
                await self._discovery.discover(server.id, announce=True)
        elif method in _MEMBER_LISTS:
            if await self._claim(server, method.split("/")[1]):
                await self._announce(server, _MEMBER_LISTS[method])
        elif method == RESOURCE_UPDATED:
            await self._resource_updated(server, notification)
        elif method == LOG_MESSAGE and bound_to is not None:
            await self._log_message(notification, bound_to)

    async def _claim(self, server: McpServer, listed: str) -> bool:
        key = REDISCOVER_KEY.format(server=server.name, list=listed)
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

    async def _resource_updated(self, server: McpServer, notification: dict[str, Any]) -> None:
        uri = (notification.get("params") or {}).get("uri")
        if not isinstance(uri, str):
            return
        subscription = ResourceSubscription(server_name=server.name, uri=uri)
        for stream_id in await self._subscriptions.streams(subscription):
            await self._signals.deliver(stream_id, notification)

    async def _log_message(self, notification: dict[str, Any], session_id: str) -> None:
        level = (notification.get("params") or {}).get("level")
        record = await self._sessions.load(session_id)
        if record is None or record.log_level is None or level not in LOG_LEVELS:
            return
        if at_least(level, record.log_level):
            await self._signals.deliver(session_id, notification)
