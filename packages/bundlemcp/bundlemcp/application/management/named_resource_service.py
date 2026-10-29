"""What every service for a resource addressed by name has in common."""

from typing import Any

from pydantic import TypeAdapter, ValidationError

from bundlemcp.application.contracts.persistence.invalidation_event import (
    EntityType,
    InvalidationEvent,
)
from bundlemcp.application.contracts.persistence.repository import NamedRepository
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.errors import InvalidInputError, NotFoundError
from bundlemcp.application.schemas import EntityRead, Page


class NamedResourceService[TEntity, TRead: EntityRead]:
    """Listing, lookup, deletion and rename for an entity with a unique ``name``.

    Subclasses add the writes that are specific to their resource; the shape of
    a page, the not-found error and the invalidation event are decided here once.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        *,
        repo: NamedRepository[TEntity],
        read_model: type[TRead],
        entity_type: EntityType,
        label: str,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._read_model = read_model
        self._entity_type = entity_type
        self._label = label

    async def _by_name(self, name: str) -> TEntity | None:
        return await self._repo.by_name(name)

    async def _get(self, name: str) -> TEntity:
        found = await self._by_name(name)
        if found is None:
            raise NotFoundError(f"{self._label} not found")
        return found

    def _read(self, entity: TEntity) -> TRead:
        return self._read_model.from_entity(entity)

    def _invalidate(self, name: str, action: str = "updated") -> None:
        self._uow.invalidate(
            InvalidationEvent(entity_type=self._entity_type, key=name, action=action)  # type: ignore[arg-type]
        )

    async def _save(self, entity: TEntity, *, name: str, created: bool) -> TRead:
        """Stage the entity, commit, and publish the matching invalidation."""
        self._repo.add(entity)
        self._invalidate(name, "created" if created else "updated")
        await self._uow.commit()
        await self._uow.refresh(entity)
        return self._read(entity)

    async def _rename(self, entity: TEntity, new_name: str, name_type: TypeAdapter[Any]) -> TRead:
        try:
            name_type.validate_python(new_name)
        except ValidationError as exc:
            raise InvalidInputError(str(exc)) from None
        entity.name = new_name  # type: ignore[attr-defined]
        return await self._save(entity, name=new_name, created=False)

    async def list(self, *, offset: int, limit: int) -> Page[TRead]:
        page_slice = await self._repo.page(offset=offset, limit=limit)
        return Page.of(page_slice, offset=offset, limit=limit, read=self._read)

    async def get(self, name: str) -> TRead:
        return self._read(await self._get(name))

    async def delete(self, name: str) -> None:
        """Idempotent: a missing resource still yields success (404 -> 204 semantics)."""
        entity = await self._by_name(name)
        if entity is None:
            return
        await self._repo.delete(entity)  # the database cascades dependants
        self._invalidate(name, "deleted")
        await self._uow.commit()
