"""A user's standing permission for one client to reach one endpoint."""

import uuid

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.domain.oauth.oauth_consent import OAuthConsent


class ConsentService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._consents = uow.consents

    async def is_granted(self, user_id: uuid.UUID, client_id: str, endpoint_id: uuid.UUID) -> bool:
        """Whether an unrevoked consent exists, so the consent screen can be skipped."""
        # OAS-11
        return await self._consents.active(user_id, client_id, endpoint_id) is not None

    async def grant(self, user_id: uuid.UUID, client_id: str, endpoint_id: uuid.UUID) -> None:
        """Record the user's approval so it is not asked for again."""
        self._consents.add(
            OAuthConsent(user_id=user_id, client_id=client_id, endpoint_id=endpoint_id)
        )
        await self._uow.commit()
