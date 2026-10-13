import uuid
from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.repository import Repository
from bundlemcp.domain.bundles.bundle_resource import BundleResource
from bundlemcp.domain.bundles.resource_listing import ResourceListing


@runtime_checkable
class BundleResourceRepository(Repository[BundleResource], Protocol):
    """Resources authored on a bundle."""

    async def find(self, bundle_id: uuid.UUID, name: str) -> BundleResource | None:
        """One resource of one bundle by name, or None."""
        ...

    async def listings(self, bundle_id: uuid.UUID) -> list[ResourceListing]:
        """Every resource of the bundle in name order, without its content."""
        ...

    async def page_for_bundle(
        self, bundle_id: uuid.UUID, *, offset: int, limit: int
    ) -> tuple[int, list[BundleResource]]:
        """One page of the bundle's resources in name order, plus the total."""
        ...
