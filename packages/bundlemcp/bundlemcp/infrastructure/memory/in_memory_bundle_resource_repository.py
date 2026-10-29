import uuid

from bundlemcp.application.contracts.persistence.page_slice import PageSlice
from bundlemcp.domain.bundles.bundle_resource import BundleResource
from bundlemcp.domain.bundles.resource_listing import ResourceListing
from bundlemcp.infrastructure.memory.in_memory_repository import InMemoryRepository

# A listing is the entity's fields minus the body.
_LISTED = set(ResourceListing.model_fields)


class InMemoryBundleResourceRepository(InMemoryRepository[BundleResource]):
    async def find(self, bundle_id: uuid.UUID, name: str) -> BundleResource | None:
        return self.first(lambda r: r.bundle_id == bundle_id and r.name == name)

    async def listings(self, bundle_id: uuid.UUID) -> list[ResourceListing]:
        resources = sorted(self.where(lambda r: r.bundle_id == bundle_id), key=lambda r: r.name)
        return [ResourceListing.model_validate(r.model_dump(include=_LISTED)) for r in resources]

    async def page_for_bundle(
        self, bundle_id: uuid.UUID, *, offset: int, limit: int
    ) -> PageSlice[BundleResource]:
        return self._page(
            self.where(lambda r: r.bundle_id == bundle_id),
            offset=offset,
            limit=limit,
            order=lambda r: r.name,
        )
