import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from bundlemcp.application.contracts.persistence.page_slice import PageSlice
from bundlemcp.domain.bundles.bundle_prompt import BundlePrompt
from bundlemcp.domain.bundles.prompt_listing import PromptListing
from bundlemcp.infrastructure.postgres.rows.bundle_prompt_row import BundlePromptRow
from bundlemcp.infrastructure.postgres.sqlalchemy_repository import SqlAlchemyRepository

_LISTING_COLUMNS = (
    BundlePromptRow.name,
    BundlePromptRow.title,
    BundlePromptRow.description,
    BundlePromptRow.arguments,
)


class SqlAlchemyBundlePromptRepository(SqlAlchemyRepository[BundlePrompt, BundlePromptRow]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, BundlePrompt, BundlePromptRow)

    async def find(self, bundle_id: uuid.UUID, name: str) -> BundlePrompt | None:
        return await self.one(BundlePromptRow.bundle_id == bundle_id, BundlePromptRow.name == name)

    async def listings(self, bundle_id: uuid.UUID) -> list[PromptListing]:
        # Messages are left in the table: a listing is read on every request.
        await self.flush_pending()
        statement = (
            select(*_LISTING_COLUMNS)
            .where(BundlePromptRow.bundle_id == bundle_id)
            .order_by(BundlePromptRow.name)
        )
        rows = (await self._session.execute(statement)).mappings()
        return [PromptListing.model_validate(dict(row)) for row in rows]

    async def page_for_bundle(
        self, bundle_id: uuid.UUID, *, offset: int, limit: int
    ) -> PageSlice[BundlePrompt]:
        return await self.page(
            BundlePromptRow.bundle_id == bundle_id,
            offset=offset,
            limit=limit,
            order_by=(BundlePromptRow.name,),
        )
