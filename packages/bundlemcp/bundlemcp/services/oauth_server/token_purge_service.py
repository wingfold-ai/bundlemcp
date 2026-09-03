"""Removing grants and tokens nothing can use any more."""

from datetime import timedelta

from sqlalchemy import delete

from bundlemcp.models import OAuthAccessToken, OAuthAuthorizationCode, OAuthClient, utcnow
from bundlemcp.store import UnitOfWork

REFRESH_GRACE = timedelta(days=1)
UNUSED_CLIENT_GRACE = timedelta(days=7)


class TokenPurgeService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def purge_expired(self) -> int:
        """Delete expired codes, long-expired token pairs and never-used clients."""
        # OAS-8 / SEC-8
        now = utcnow()
        session = self._uow.session
        removed = 0
        for statement in (
            delete(OAuthAuthorizationCode).where(OAuthAuthorizationCode.expires_at < now),
            delete(OAuthAccessToken).where(
                OAuthAccessToken.refresh_expires_at < now - REFRESH_GRACE
            ),
            delete(OAuthClient).where(
                OAuthClient.last_used_at.is_(None),  # type: ignore[union-attr]
                OAuthClient.created_at < now - UNUSED_CLIENT_GRACE,
            ),
        ):
            result = await session.execute(statement)
            removed += result.rowcount or 0
        await self._uow.commit()
        return removed
