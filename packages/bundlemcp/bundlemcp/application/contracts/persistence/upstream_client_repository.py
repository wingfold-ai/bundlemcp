import uuid
from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.repository import Repository
from bundlemcp.domain.upstream_oauth.upstream_oauth_client import UpstreamOAuthClient


@runtime_checkable
class UpstreamClientRepository(Repository[UpstreamOAuthClient], Protocol):
    """The gateway's pre-registered client at each server's authorization server."""

    async def for_server(self, server_id: uuid.UUID) -> UpstreamOAuthClient | None:
        """The client registration for one server, or None."""
        ...
