from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.upstream.member_notification import MemberNotification
from bundlemcp.domain.servers.mcp_server import McpServer


@runtime_checkable
class UpstreamNotificationSink(Protocol):
    """Where a notification an upstream sends outside any request's response goes."""

    async def received(
        self, server: McpServer, notification: MemberNotification, *, bound_to: str | None
    ) -> None:
        """Act on ``notification`` from ``server``.

        ``bound_to`` names the handshake session the upstream session is
        dedicated to, or is None for a session shared between requests.
        """
        ...
