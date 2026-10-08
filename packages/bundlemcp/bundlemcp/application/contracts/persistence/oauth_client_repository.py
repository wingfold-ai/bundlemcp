from datetime import datetime
from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.repository import Repository
from bundlemcp.domain.oauth.oauth_client import OAuthClient


@runtime_checkable
class OAuthClientRepository(Repository[OAuthClient], Protocol):
    """Clients of the gateway's own authorization server."""

    async def count_never_used(self) -> int:
        """How many clients have never obtained a token."""
        ...

    async def purge_never_used(self, *, created_before: datetime) -> int:
        """Delete clients that registered before this time and never obtained a token."""
        ...
