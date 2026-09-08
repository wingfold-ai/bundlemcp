import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.domain.endpoints.endpoint import Endpoint
from bundlemcp.infrastructure.postgres.rows.endpoint_row import EndpointRow
from bundlemcp.infrastructure.postgres.sqlalchemy_repository import SqlAlchemyRepository


class SqlAlchemyEndpointRepository(SqlAlchemyRepository[Endpoint, EndpointRow]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Endpoint, EndpointRow)

    async def for_bundle(self, bundle_id: uuid.UUID) -> list[Endpoint]:
        return await self.all(EndpointRow.bundle_id == bundle_id)

    async def page(self, *, offset: int, limit: int) -> tuple[int, list[Endpoint]]:
        return await super().page(
            offset=offset, limit=limit, order_by=(EndpointRow.created_at, EndpointRow.id)
        )
