import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.domain.bundles.bundle_tool import BundleTool
from bundlemcp.infrastructure.postgres.rows.bundle_tool_row import BundleToolRow
from bundlemcp.infrastructure.postgres.sqlalchemy_repository import SqlAlchemyRepository


class SqlAlchemyCurationRepository(SqlAlchemyRepository[BundleTool, BundleToolRow]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, BundleTool, BundleToolRow)

    async def for_bundle(self, bundle_id: uuid.UUID) -> list[BundleTool]:
        return await self.all(BundleToolRow.bundle_id == bundle_id)

    async def find(self, bundle_id: uuid.UUID, tool_id: uuid.UUID) -> BundleTool | None:
        return await self.one(
            BundleToolRow.bundle_id == bundle_id, BundleToolRow.tool_id == tool_id
        )

    async def override_name_taken(
        self, bundle_id: uuid.UUID, override_name: str, *, except_tool_id: uuid.UUID
    ) -> bool:
        clash = await self.one(
            BundleToolRow.bundle_id == bundle_id,
            BundleToolRow.override_name == override_name,
            BundleToolRow.tool_id != except_tool_id,
        )
        return clash is not None
