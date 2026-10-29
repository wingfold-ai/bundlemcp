from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.application.contracts.persistence.page_slice import PageSlice
from bundlemcp.domain.access.user import User
from bundlemcp.infrastructure.postgres.rows.user_row import UserRow
from bundlemcp.infrastructure.postgres.sqlalchemy_repository import SqlAlchemyRepository


class SqlAlchemyUserRepository(SqlAlchemyRepository[User, UserRow]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User, UserRow)

    async def by_subject(self, issuer: str, sub: str) -> User | None:
        return await self.one(UserRow.oidc_issuer == issuer, UserRow.oidc_sub == sub)

    async def page(self, *, offset: int, limit: int) -> PageSlice[User]:
        return await super().page(
            offset=offset, limit=limit, order_by=(UserRow.created_at, UserRow.id)
        )
