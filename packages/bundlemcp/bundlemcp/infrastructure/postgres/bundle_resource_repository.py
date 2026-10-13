import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from bundlemcp.domain.bundles.bundle_resource import BundleResource
from bundlemcp.domain.bundles.resource_listing import ResourceListing
from bundlemcp.infrastructure.postgres.rows.bundle_resource_row import BundleResourceRow
from bundlemcp.infrastructure.postgres.sqlalchemy_repository import SqlAlchemyRepository

_LISTING_COLUMNS = (
    BundleResourceRow.name,
    BundleResourceRow.title,
    BundleResourceRow.description,
    BundleResourceRow.mime_type,
    BundleResourceRow.size_bytes,
)


class SqlAlchemyBundleResourceRepository(SqlAlchemyRepository[BundleResource, BundleResourceRow]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, BundleResource, BundleResourceRow)

    async def find(self, bundle_id: uuid.UUID, name: str) -> BundleResource | None:
        return await self.one(
            BundleResourceRow.bundle_id == bundle_id, BundleResourceRow.name == name
        )

    async def listings(self, bundle_id: uuid.UUID) -> list[ResourceListing]:
        # Content is left in the table: a listing is read on every request.
        await self.flush_pending()
        statement = (
            select(*_LISTING_COLUMNS)
            .where(BundleResourceRow.bundle_id == bundle_id)
            .order_by(BundleResourceRow.name)
        )
        rows = (await self._session.execute(statement)).mappings()
        return [ResourceListing.model_validate(dict(row)) for row in rows]

    async def page_for_bundle(
        self, bundle_id: uuid.UUID, *, offset: int, limit: int
    ) -> tuple[int, list[BundleResource]]:
        return await self.page(
            BundleResourceRow.bundle_id == bundle_id,
            offset=offset,
            limit=limit,
            order_by=(BundleResourceRow.name,),
        )
