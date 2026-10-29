from bundlemcp.application.contracts.live_state.resource_subscriptions import (
    ResourceSubscription,
    ResourceSubscriptions,
)
from bundlemcp.application.contracts.live_state.signal_bus import SignalBus
from bundlemcp.application.contracts.upstream.member_notification import MemberResourceUpdated
from bundlemcp.domain.servers.mcp_server import McpServer


class MemberResourceUpdateHandler:
    """Delivers a member resource's update to every stream subscribed to it, on any replica."""

    def __init__(self, subscriptions: ResourceSubscriptions, signals: SignalBus) -> None:
        self._subscriptions = subscriptions
        self._signals = signals

    async def handle(
        self, server: McpServer, notification: MemberResourceUpdated, *, bound_to: str | None
    ) -> None:
        subscription = ResourceSubscription(server_name=server.name, uri=notification.uri)
        for stream_id in await self._subscriptions.streams(subscription):
            await self._signals.deliver(stream_id, notification.notification())
