import uuid
from datetime import datetime

from bundlemcp.domain.oauth.oauth_consent import OAuthConsent
from bundlemcp.infrastructure.memory.in_memory_repository import InMemoryRepository


class InMemoryConsentRepository(InMemoryRepository[OAuthConsent]):
    async def active(
        self, user_id: uuid.UUID, client_id: str, endpoint_id: uuid.UUID
    ) -> OAuthConsent | None:
        return self.first(
            lambda c: (
                c.user_id == user_id
                and c.client_id == client_id
                and c.endpoint_id == endpoint_id
                and c.is_active
            )
        )

    async def active_for_user(self, user_id: uuid.UUID) -> list[OAuthConsent]:
        return self.where(lambda c: c.user_id == user_id and c.is_active)

    async def find(self, user_id: uuid.UUID, consent_id: uuid.UUID) -> OAuthConsent | None:
        return self.first(lambda c: c.id == consent_id and c.user_id == user_id)

    async def revoke_for_user(self, user_id: uuid.UUID, *, at: datetime) -> None:
        for consent in self.where(lambda c: c.user_id == user_id and c.is_active):
            consent.revoke(at)
