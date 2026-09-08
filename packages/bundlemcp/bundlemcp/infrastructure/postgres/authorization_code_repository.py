from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.domain.oauth.oauth_authorization_code import OAuthAuthorizationCode
from bundlemcp.infrastructure.postgres.rows.oauth_authorization_code_row import (
    OAuthAuthorizationCodeRow,
)
from bundlemcp.infrastructure.postgres.sqlalchemy_repository import SqlAlchemyRepository


class SqlAlchemyAuthorizationCodeRepository(
    SqlAlchemyRepository[OAuthAuthorizationCode, OAuthAuthorizationCodeRow]
):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(
            session,
            OAuthAuthorizationCode,
            OAuthAuthorizationCodeRow,
            key=lambda code: code.code_hash,
        )

    async def burn(self, code_hash: str) -> bool:
        burned = await self.update_where(
            OAuthAuthorizationCodeRow.code_hash == code_hash,
            OAuthAuthorizationCodeRow.used.is_(False),  # type: ignore[union-attr]
            used=True,
        )
        return burned == 1

    async def purge_expired(self, *, expired_before: datetime) -> int:
        return await self.delete_where(OAuthAuthorizationCodeRow.expires_at < expired_before)
