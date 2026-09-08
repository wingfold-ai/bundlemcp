"""Removing grants and tokens nothing can use any more."""

from datetime import timedelta

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.domain.shared.clock import utcnow

REFRESH_GRACE = timedelta(days=1)
UNUSED_CLIENT_GRACE = timedelta(days=7)


class TokenPurgeService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def purge_expired(self) -> int:
        """Delete expired codes, long-expired token pairs and never-used clients."""
        # OAS-8 / SEC-8
        now = utcnow()
        removed = await self._uow.authorization_codes.purge_expired(expired_before=now)
        removed += await self._uow.oauth_tokens.purge_expired(
            refresh_expired_before=now - REFRESH_GRACE
        )
        removed += await self._uow.oauth_clients.purge_never_used(
            created_before=now - UNUSED_CLIENT_GRACE
        )
        await self._uow.commit()
        return removed
