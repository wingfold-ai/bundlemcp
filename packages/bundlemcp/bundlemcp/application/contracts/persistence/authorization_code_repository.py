from datetime import datetime
from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.repository import Repository
from bundlemcp.domain.oauth.oauth_authorization_code import OAuthAuthorizationCode


@runtime_checkable
class AuthorizationCodeRepository(Repository[OAuthAuthorizationCode], Protocol):
    """Single-use authorization codes, keyed by the hash of the code."""

    async def burn(self, code_hash: str) -> bool:
        """Mark a code used as a compare-and-set; False when it was used already."""
        ...

    async def purge_expired(self, *, expired_before: datetime) -> int:
        """Delete codes that expired before this time."""
        ...
