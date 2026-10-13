"""Prompts authored on a bundle."""

# lazy annotations: `list[...]` in the class body would otherwise resolve to
# the `list` method on Python < 3.14
from __future__ import annotations

import uuid

import structlog

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.errors import InvalidInputError, NotFoundError
from bundlemcp.application.management.bundle_content_service import BundleContentService
from bundlemcp.application.schemas import (
    BundlePromptRead,
    BundlePromptUpsert,
    CataloguePromptRead,
    Page,
)
from bundlemcp.domain.bundles.bundle_content_limits import DEFAULT_LIMITS, BundleContentLimits
from bundlemcp.domain.bundles.bundle_content_rejected import BundleContentRejected
from bundlemcp.domain.bundles.bundle_prompt import BundlePrompt

log = structlog.get_logger(__name__)


class BundlePromptService(BundleContentService):
    def __init__(self, uow: UnitOfWork, limits: BundleContentLimits = DEFAULT_LIMITS) -> None:
        super().__init__(uow, entity_type="bundle_prompt", limits=limits)
        self._prompts = uow.bundle_prompts

    async def list(self, bundle_name: str, *, offset: int, limit: int) -> Page[BundlePromptRead]:
        bundle = await self._bundle(bundle_name)
        total, rows = await self._prompts.page_for_bundle(bundle.id, offset=offset, limit=limit)
        return Page.of(rows, total, offset=offset, limit=limit, read=BundlePromptRead.from_entity)

    async def get(self, bundle_name: str, name: str) -> BundlePromptRead:
        bundle = await self._bundle(bundle_name)
        prompt = await self._prompts.find(bundle.id, name)
        if prompt is None:
            raise NotFoundError("prompt not found")
        return BundlePromptRead.from_entity(prompt)

    async def catalogue(self, bundle_id: uuid.UUID) -> list[CataloguePromptRead]:
        """The bundle's own prompts as a person browsing the catalogue sees them."""
        # BPR-19
        return [
            CataloguePromptRead(name=p.name, title=p.title, description=p.description)
            for p in await self._prompts.listings(bundle_id)
        ]

    async def upsert(self, bundle_name: str, body: BundlePromptUpsert) -> BundlePromptRead:
        """Create or replace a prompt; idempotent for the same body."""
        bundle = await self._bundle(bundle_name)
        existing = await self._prompts.find(bundle.id, body.name)
        prompt = BundlePrompt(bundle_id=bundle.id, **body.model_dump())
        if existing is not None:
            prompt.id, prompt.created_at = existing.id, existing.created_at
        listings = await self._prompts.listings(bundle.id)
        resources = await self._uow.bundle_resources.listings(bundle.id)
        try:
            prompt.check_references({resource.name for resource in resources})  # BPR-3
            self._limits.check_prompt(  # BPR-16
                prompt, prompts_after=len(listings) + (existing is None)
            )
        except BundleContentRejected as exc:
            raise InvalidInputError(str(exc)) from None
        self._prompts.add(prompt)
        await self._commit(bundle, "created" if existing is None else "updated")
        await self._uow.refresh(prompt)
        # BPR-17: content is configuration, so it is logged by size, never by value
        log.info(
            "bundle_prompt.saved", bundle=bundle.name, prompt=prompt.name, bytes=prompt.text_bytes
        )
        return BundlePromptRead.from_entity(prompt)

    async def delete(self, bundle_name: str, name: str) -> None:
        """Idempotent: a missing prompt still yields success."""
        bundle = await self._bundle(bundle_name)
        prompt = await self._prompts.find(bundle.id, name)
        if prompt is None:
            return
        await self._prompts.delete(prompt)
        await self._commit(bundle, "deleted")
        log.info("bundle_prompt.deleted", bundle=bundle.name, prompt=name)
