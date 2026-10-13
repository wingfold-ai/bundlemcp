import uuid
from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.repository import Repository
from bundlemcp.domain.bundles.bundle_server import BundleServer


@runtime_checkable
class MembershipRepository(Repository[BundleServer], Protocol):
    """Which servers belong to which bundles."""

    async def for_bundle(self, bundle_id: uuid.UUID) -> list[BundleServer]:
        """Every membership of one bundle, in member order."""
        ...

    async def for_server(self, server_id: uuid.UUID) -> list[BundleServer]:
        """Every bundle one server belongs to."""
        ...

    async def find(self, bundle_id: uuid.UUID, server_id: uuid.UUID) -> BundleServer | None:
        """The membership of one server in one bundle, or None."""
        ...
