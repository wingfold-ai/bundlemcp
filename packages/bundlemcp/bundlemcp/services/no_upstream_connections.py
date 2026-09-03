from uuid import UUID

from bundlemcp.schemas import UpstreamConnectionStatus


class NoUpstreamConnections:
    """The registry in a gateway without token encryption keys: nothing is ever connected."""

    @property
    def configured(self) -> bool:
        return False

    async def status(self, server_id: UUID, user_id: UUID | None) -> UpstreamConnectionStatus:
        return UpstreamConnectionStatus()

    async def disconnect(self, server_id: UUID, user_id: UUID | None) -> None:
        return None
