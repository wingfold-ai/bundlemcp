import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.domain.bundles.bundle_server import BundleServer
from bundlemcp.infrastructure.postgres.rows.bundle_server_row import BundleServerRow
from bundlemcp.infrastructure.postgres.sqlalchemy_repository import SqlAlchemyRepository


class SqlAlchemyMembershipRepository(SqlAlchemyRepository[BundleServer, BundleServerRow]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, BundleServer, BundleServerRow)

    async def for_bundle(self, bundle_id: uuid.UUID) -> list[BundleServer]:
        return await self.all(BundleServerRow.bundle_id == bundle_id)

    async def for_server(self, server_id: uuid.UUID) -> list[BundleServer]:
        return await self.all(BundleServerRow.server_id == server_id)

    async def find(self, bundle_id: uuid.UUID, server_id: uuid.UUID) -> BundleServer | None:
        return await self.one(
            BundleServerRow.bundle_id == bundle_id, BundleServerRow.server_id == server_id
        )
