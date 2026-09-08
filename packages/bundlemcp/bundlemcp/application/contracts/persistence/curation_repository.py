import uuid
from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.repository import Repository
from bundlemcp.domain.bundles.bundle_tool import BundleTool


@runtime_checkable
class CurationRepository(Repository[BundleTool], Protocol):
    """Per-bundle tool curation: enablement and overrides."""

    async def for_bundle(self, bundle_id: uuid.UUID) -> list[BundleTool]:
        """Every curation record of one bundle."""
        ...

    async def find(self, bundle_id: uuid.UUID, tool_id: uuid.UUID) -> BundleTool | None:
        """The curation of one tool in one bundle, or None."""
        ...

    async def override_name_taken(
        self, bundle_id: uuid.UUID, override_name: str, *, except_tool_id: uuid.UUID
    ) -> bool:
        """Whether another tool in the bundle already presents itself under this name."""
        ...
