import uuid
from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.repository import NamedRepository
from bundlemcp.domain.servers.mcp_server import McpServer


@runtime_checkable
class ServerRepository(NamedRepository[McpServer], Protocol):
    """Registered upstream servers."""

    async def by_ids(self, ids: Iterable[uuid.UUID]) -> list[McpServer]:
        """The servers with these ids, in name order; unknown ids are skipped."""
        ...
