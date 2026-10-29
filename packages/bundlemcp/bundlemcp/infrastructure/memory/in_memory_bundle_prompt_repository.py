import uuid

from bundlemcp.application.contracts.persistence.page_slice import PageSlice
from bundlemcp.domain.bundles.bundle_prompt import BundlePrompt
from bundlemcp.domain.bundles.prompt_listing import PromptListing
from bundlemcp.infrastructure.memory.in_memory_repository import InMemoryRepository

# A listing is the entity's fields minus the body.
_LISTED = set(PromptListing.model_fields)


class InMemoryBundlePromptRepository(InMemoryRepository[BundlePrompt]):
    async def find(self, bundle_id: uuid.UUID, name: str) -> BundlePrompt | None:
        return self.first(lambda p: p.bundle_id == bundle_id and p.name == name)

    async def listings(self, bundle_id: uuid.UUID) -> list[PromptListing]:
        prompts = sorted(self.where(lambda p: p.bundle_id == bundle_id), key=lambda p: p.name)
        return [PromptListing.model_validate(p.model_dump(include=_LISTED)) for p in prompts]

    async def page_for_bundle(
        self, bundle_id: uuid.UUID, *, offset: int, limit: int
    ) -> PageSlice[BundlePrompt]:
        return self._page(
            self.where(lambda p: p.bundle_id == bundle_id),
            offset=offset,
            limit=limit,
            order=lambda p: p.name,
        )
