"""Documents authored on a bundle."""

# lazy annotations: `list[...]` in the class body would otherwise resolve to
# the `list` method on Python < 3.14
from __future__ import annotations

import uuid

import structlog

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.errors import ConflictError, InvalidInputError, NotFoundError
from bundlemcp.application.management.bundle_content_service import BundleContentService
from bundlemcp.application.schemas import (
    BundleResourceRead,
    BundleResourceUpsert,
    CatalogueResourceRead,
    Page,
)
from bundlemcp.domain.bundles.bundle import Bundle
from bundlemcp.domain.bundles.bundle_content_limits import DEFAULT_LIMITS, BundleContentLimits
from bundlemcp.domain.bundles.bundle_content_rejected import BundleContentRejected
from bundlemcp.domain.bundles.bundle_resource import BundleResource

log = structlog.get_logger(__name__)


class BundleResourceService(BundleContentService):
    def __init__(self, uow: UnitOfWork, limits: BundleContentLimits = DEFAULT_LIMITS) -> None:
        super().__init__(uow, entity_type="bundle_resource", limits=limits)
        self._resources = uow.bundle_resources

    async def list(self, bundle_name: str, *, offset: int, limit: int) -> Page[BundleResourceRead]:
        bundle = await self._bundle(bundle_name)
        page_slice = await self._resources.page_for_bundle(bundle.id, offset=offset, limit=limit)
        return Page.of(page_slice, offset=offset, limit=limit, read=BundleResourceRead.from_entity)

    async def get(self, bundle_name: str, name: str) -> BundleResourceRead:
        bundle = await self._bundle(bundle_name)
        resource = await self._resources.find(bundle.id, name)
        if resource is None:
            raise NotFoundError("resource not found")
        return BundleResourceRead.from_entity(resource)

    async def catalogue(self, bundle_id: uuid.UUID) -> list[CatalogueResourceRead]:
        """The bundle's own resources as a person browsing the catalogue sees them."""
        return [
            CatalogueResourceRead(name=r.name, title=r.title, description=r.description)
            for r in await self._resources.listings(bundle_id)
        ]

    async def upsert(self, bundle_name: str, body: BundleResourceUpsert) -> BundleResourceRead:
        """Create or replace a resource; idempotent for the same body."""
        bundle = await self._bundle(bundle_name)
        existing = await self._resources.find(bundle.id, body.name)
        resource = BundleResource(bundle_id=bundle.id, **body.model_dump())
        if existing is not None:
            resource.id, resource.created_at = existing.id, existing.created_at
        others = [r for r in await self._resources.listings(bundle.id) if r.name != body.name]
        try:
            self._limits.check_resource(
                resource,
                resources_after=len(others) + 1,
                bundle_bytes_after=sum(r.size_bytes for r in others) + resource.size_bytes,
            )
        except BundleContentRejected as exc:
            raise InvalidInputError(str(exc)) from None
        self._resources.add(resource)
        await self._commit(bundle, "created" if existing is None else "updated")
        await self._uow.refresh(resource)
        # content is configuration, so it is logged by size, never by value
        log.info(
            "bundle_resource.saved",
            bundle=bundle.name,
            resource=resource.name,
            bytes=resource.size_bytes,
        )
        return BundleResourceRead.from_entity(resource)

    async def delete(self, bundle_name: str, name: str) -> None:
        """Idempotent: a missing resource still yields success.

        A resource a prompt embeds is kept, so no prompt is left pointing at
        nothing; the error names the prompts to change first.
        """
        bundle = await self._bundle(bundle_name)
        resource = await self._resources.find(bundle.id, name)
        if resource is None:
            return
        if embedding := await self._embedding_prompts(bundle, name):
            raise ConflictError(
                f"resource is embedded by prompts {', '.join(embedding)}; change them first"
            )
        await self._resources.delete(resource)
        await self._commit(bundle, "deleted")
        log.info("bundle_resource.deleted", bundle=bundle.name, resource=name)

    async def _embedding_prompts(self, bundle: Bundle, name: str) -> list[str]:
        prompts = (
            await self._uow.bundle_prompts.page_for_bundle(
                bundle.id, offset=0, limit=self._limits.max_prompts
            )
        ).items
        return [prompt.name for prompt in prompts if name in prompt.resource_names]
