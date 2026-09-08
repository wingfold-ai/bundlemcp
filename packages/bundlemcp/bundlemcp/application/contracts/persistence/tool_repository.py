import uuid
from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.repository import Repository
from bundlemcp.domain.servers.tool import Tool


@runtime_checkable
class ToolRepository(Repository[Tool], Protocol):
    """Tool definitions cached from discovery, owned by their server."""

    async def for_server(self, server_id: uuid.UUID) -> list[Tool]:
        """Every tool of one server, in name order."""
        ...

    async def for_servers(self, server_ids: Iterable[uuid.UUID]) -> list[Tool]:
        """Every tool of the given servers, in name order."""
        ...

    async def page_for_server(
        self, server_id: uuid.UUID, *, offset: int, limit: int
    ) -> tuple[int, list[Tool]]:
        """One page of a server's tools in name order, plus the total."""
        ...
