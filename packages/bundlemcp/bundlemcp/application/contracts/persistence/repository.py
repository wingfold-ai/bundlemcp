"""What every repository port offers, whatever the entity."""

from typing import Any, Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.page_slice import PageSlice


@runtime_checkable
class Repository[T](Protocol):
    """Reads and stages changes to one kind of entity.

    A repository owns no transaction: the unit of work that handed it out
    commits. Queries speak in entity terms; no storage vocabulary crosses this
    boundary.
    """

    async def get(self, id_: Any) -> T | None:
        """The entity with this primary key, or None."""
        ...

    def add(self, entity: T) -> T:
        """Stage a new or changed entity for the enclosing commit."""
        ...

    async def delete(self, entity: T) -> None:
        """Stage the removal of an entity for the enclosing commit."""
        ...


@runtime_checkable
class NamedRepository[T](Repository[T], Protocol):
    """A repository for an entity addressed by a unique ``name``."""

    async def by_name(self, name: str) -> T | None:
        """The entity with this natural key, or None."""
        ...

    async def page(self, *, offset: int, limit: int) -> PageSlice[T]:
        """One page in creation order, plus the total the page was cut from."""
        ...
