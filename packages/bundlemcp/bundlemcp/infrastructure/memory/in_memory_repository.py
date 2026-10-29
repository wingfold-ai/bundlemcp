"""The dict-backed repository every in-memory fake builds on."""

from collections.abc import Callable, Iterable
from typing import Any

from pydantic import BaseModel

from bundlemcp.application.contracts.persistence.page_slice import PageSlice


class InMemoryRepository[T: BaseModel]:
    """Entities held in a dict by primary key; mutations to a stored object persist at once.

    First-class, not test junk: it proves the ports are storage-neutral and it
    is what use-case tests run on.
    """

    def __init__(self, key: Callable[[T], Any] = lambda entity: entity.id) -> None:  # type: ignore[attr-defined]
        self._key = key
        self._rows: dict[Any, T] = {}

    @property
    def rows(self) -> list[T]:
        return list(self._rows.values())

    async def get(self, id_: Any) -> T | None:
        return self._rows.get(id_)

    def add(self, entity: T) -> T:
        self._rows[self._key(entity)] = entity
        return entity

    async def delete(self, entity: T) -> None:
        self._rows.pop(self._key(entity), None)

    def where(self, predicate: Callable[[T], bool]) -> list[T]:
        return [row for row in self._rows.values() if predicate(row)]

    def first(self, predicate: Callable[[T], bool]) -> T | None:
        return next((row for row in self._rows.values() if predicate(row)), None)

    async def by_name(self, name: str) -> T | None:
        return self.first(lambda row: row.name == name)  # type: ignore[attr-defined]

    def _page(
        self, rows: Iterable[T], *, offset: int, limit: int, order: Callable[[T], Any]
    ) -> PageSlice[T]:
        ordered = sorted(rows, key=order)
        return PageSlice(items=ordered[offset : offset + limit], total=len(ordered))

    async def page(self, *, offset: int, limit: int) -> PageSlice[T]:
        return self._page(
            self._rows.values(),
            offset=offset,
            limit=limit,
            order=lambda row: (row.created_at, str(row.id)),  # type: ignore[attr-defined]
        )
