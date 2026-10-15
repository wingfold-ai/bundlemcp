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

    async def replace_ciphertext(self, id: uuid.UUID, expected: str, new: str) -> bool:
        """Store ``new`` in place of ``expected`` only if the row still holds ``expected``.

        False when another write changed the value first; nothing is changed then.
        """
        ...

    async def page_after(self, after: uuid.UUID | None, limit: int) -> list[UpstreamOAuthClient]:
        """Up to ``limit`` rows in id order, starting after ``after`` (from the start on None)."""
        ...
