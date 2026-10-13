import uuid
from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.repository import Repository
from bundlemcp.domain.bundles.bundle_prompt import BundlePrompt
from bundlemcp.domain.bundles.prompt_listing import PromptListing


@runtime_checkable
class BundlePromptRepository(Repository[BundlePrompt], Protocol):
    """Prompts authored on a bundle."""

    async def find(self, bundle_id: uuid.UUID, name: str) -> BundlePrompt | None:
        """One prompt of one bundle by name, or None."""
        ...

    async def listings(self, bundle_id: uuid.UUID) -> list[PromptListing]:
        """Every prompt of the bundle in name order, without its messages."""
        ...

    async def page_for_bundle(
        self, bundle_id: uuid.UUID, *, offset: int, limit: int
    ) -> tuple[int, list[BundlePrompt]]:
        """One page of the bundle's prompts in name order, plus the total."""
        ...
