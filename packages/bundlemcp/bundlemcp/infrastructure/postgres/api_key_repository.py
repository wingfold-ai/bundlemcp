from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.application.contracts.persistence.page_slice import PageSlice
from bundlemcp.domain.access.api_key import ApiKey
from bundlemcp.domain.access.api_key_kind import ApiKeyKind
from bundlemcp.infrastructure.postgres.rows.api_key_row import ApiKeyRow
from bundlemcp.infrastructure.postgres.sqlalchemy_repository import SqlAlchemyRepository


class SqlAlchemyApiKeyRepository(SqlAlchemyRepository[ApiKey, ApiKeyRow]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ApiKey, ApiKeyRow)

    async def by_hash(self, key_hash: str) -> ApiKey | None:
        return await self.one(ApiKeyRow.key_hash == key_hash)

    async def any_of_kind(self, kind: ApiKeyKind) -> ApiKey | None:
        return await self.first(
            ApiKeyRow.kind == kind, order_by=(ApiKeyRow.created_at, ApiKeyRow.id)
        )

    async def page(self, *, offset: int, limit: int) -> PageSlice[ApiKey]:
        return await super().page(
            offset=offset, limit=limit, order_by=(ApiKeyRow.created_at, ApiKeyRow.id)
        )
