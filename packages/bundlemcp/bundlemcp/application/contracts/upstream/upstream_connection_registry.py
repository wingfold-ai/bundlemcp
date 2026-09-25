from typing import Protocol, runtime_checkable
from uuid import UUID

from bundlemcp.application.schemas import UpstreamConnectionStatus
from bundlemcp.domain.servers.mcp_server import McpServer


@runtime_checkable
class UpstreamConnectionRegistry(Protocol):
    """The upstream OAuth connections a server has, as the management API sees them."""

    @property
    def configured(self) -> bool:
        """Whether this gateway can hold upstream tokens at all."""
        ...

    async def status(self, server_id: UUID, user_id: UUID | None) -> UpstreamConnectionStatus:
        """Connection state only; never token values."""
        ...

    async def disconnect(self, server_id: UUID, user_id: UUID | None) -> None:
        """Forget the stored token set, forcing a reconnect."""
        ...

    async def connect_as_client(self, server: McpServer) -> None:
        """Obtain the shared connection of a client-credentials client now."""
        ...
