"""What the services for a bundle's own prompts and resources have in common."""

from typing import Literal

from bundlemcp.application.contracts.persistence.invalidation_event import InvalidationEvent
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.errors import NotFoundError
from bundlemcp.domain.bundles.bundle import Bundle
from bundlemcp.domain.bundles.bundle_content_limits import BundleContentLimits


class BundleContentService:
    """Content authored on a bundle: found through the bundle's name, announced as the
    bundle's change.

    A write is announced under the bundle's name, so every replica can tell the
    streams of that bundle which list changed.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        *,
        entity_type: Literal["bundle_prompt", "bundle_resource"],
        limits: BundleContentLimits,
    ) -> None:
        self._uow = uow
        self._entity_type = entity_type
        self._limits = limits

    async def _bundle(self, name: str) -> Bundle:
        bundle = await self._uow.bundles.by_name(name)
        if bundle is None:
            raise NotFoundError("bundle not found")
        return bundle

    async def _commit(
        self, bundle: Bundle, action: Literal["created", "updated", "deleted"]
    ) -> None:
        # BND-28: the bundle's view changed, so its clients' lists did too
        self._uow.invalidate(
            InvalidationEvent(entity_type=self._entity_type, key=bundle.name, action=action)
        )
        await self._uow.commit()
