import uuid
from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.repository import Repository
from bundlemcp.domain.upstream_oauth.upstream_oauth_token import UpstreamOAuthToken


@runtime_checkable
class UpstreamTokenRepository(Repository[UpstreamOAuthToken], Protocol):
    """Encrypted upstream token sets, one per (server, user); a NULL user is the shared one."""

    async def find(
        self, server_id: uuid.UUID, user_id: uuid.UUID | None
    ) -> UpstreamOAuthToken | None:
        """The connection of one user (or the shared one) to one server, or None."""
        ...

    async def any_valid_user_connection(self, server_id: uuid.UUID) -> UpstreamOAuthToken | None:
        """Some user's still-valid connection to one server, or None when nobody has one."""
        ...
