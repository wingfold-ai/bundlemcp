import uuid
from datetime import datetime
from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.repository import Repository
from bundlemcp.domain.oauth.oauth_consent import OAuthConsent


@runtime_checkable
class ConsentRepository(Repository[OAuthConsent], Protocol):
    """A user's standing consent for a client to reach an endpoint."""

    async def active(
        self, user_id: uuid.UUID, client_id: str, endpoint_id: uuid.UUID
    ) -> OAuthConsent | None:
        """The unrevoked consent for this user, client and endpoint, or None."""
        ...

    async def active_for_user(self, user_id: uuid.UUID) -> list[OAuthConsent]:
        """Every unrevoked consent one user has given."""
        ...

    async def find(self, user_id: uuid.UUID, consent_id: uuid.UUID) -> OAuthConsent | None:
        """One consent by id, provided it belongs to this user."""
        ...

    async def revoke_for_user(self, user_id: uuid.UUID, *, at: datetime) -> None:
        """Revoke every unrevoked consent one user has given."""
        ...
