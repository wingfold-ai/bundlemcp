import uuid
from datetime import datetime
from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.repository import Repository
from bundlemcp.domain.oauth.oauth_access_token import OAuthAccessToken


@runtime_checkable
class OAuthTokenRepository(Repository[OAuthAccessToken], Protocol):
    """Access/refresh token pairs issued by the gateway, stored as hashes."""

    async def by_access_hash(self, digest: str) -> OAuthAccessToken | None:
        """The pair whose access token hashes to this value, or None."""
        ...

    async def by_refresh_hash(self, digest: str) -> OAuthAccessToken | None:
        """The pair whose refresh token hashes to this value, or None."""
        ...

    async def by_either_hash(self, digest: str) -> OAuthAccessToken | None:
        """The pair whose access or refresh token hashes to this value, or None."""
        ...

    async def revoke_unless_revoked(self, token_id: uuid.UUID) -> bool:
        """Revoke one pair as a compare-and-set; False when it was already revoked."""
        ...

    async def revoke_family(self, family_id: uuid.UUID) -> None:
        """Revoke every pair descended from one grant."""
        ...

    async def revoke_for_user(self, user_id: uuid.UUID) -> None:
        """Revoke every pair issued to one user."""
        ...

    async def revoke_for_consent(
        self, user_id: uuid.UUID, client_id: str, endpoint_id: uuid.UUID
    ) -> None:
        """Revoke every pair issued under one user's consent to one client for one endpoint."""
        ...

    async def purge_expired(self, *, refresh_expired_before: datetime) -> int:
        """Delete pairs whose refresh token expired before this time."""
        ...
