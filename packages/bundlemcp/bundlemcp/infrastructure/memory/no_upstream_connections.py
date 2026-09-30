from uuid import UUID

from bundlemcp.application.errors import PreconditionError
from bundlemcp.application.schemas import UpstreamConnectionStatus
from bundlemcp.domain.servers.mcp_server import McpServer


class NoUpstreamConnections:
    """The registry in a gateway without token encryption keys: nothing is ever connected."""

    @property
    def configured(self) -> bool:
        return False

    async def status(self, server_id: UUID, user_id: UUID | None) -> UpstreamConnectionStatus:
        return UpstreamConnectionStatus()

    async def disconnect(self, server_id: UUID, user_id: UUID | None) -> None:
        return None

    async def connect_as_client(self, server: McpServer) -> None:
        raise PreconditionError("token encryption keys required for upstream OAuth (DEP-9)")
