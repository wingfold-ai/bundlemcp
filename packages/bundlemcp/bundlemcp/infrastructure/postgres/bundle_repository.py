from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.domain.bundles.bundle import Bundle
from bundlemcp.infrastructure.postgres.rows.bundle_row import BundleRow
from bundlemcp.infrastructure.postgres.sqlalchemy_repository import SqlAlchemyRepository


class SqlAlchemyBundleRepository(SqlAlchemyRepository[Bundle, BundleRow]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Bundle, BundleRow)

    async def page(self, *, offset: int, limit: int) -> tuple[int, list[Bundle]]:
        return await super().page(
            offset=offset, limit=limit, order_by=(BundleRow.created_at, BundleRow.id)
        )
