from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from bundlemcp.domain.servers.mcp_server import McpServer


@runtime_checkable
class MemberNotificationHandler[N: BaseModel](Protocol):
    """Acts on one kind of member notification."""

    async def handle(self, server: McpServer, notification: N, *, bound_to: str | None) -> None:
        """Act on ``notification`` from ``server``.

        ``bound_to`` names the handshake session the upstream session that
        heard it is dedicated to, or is None for a session shared between
        requests.
        """
        ...
