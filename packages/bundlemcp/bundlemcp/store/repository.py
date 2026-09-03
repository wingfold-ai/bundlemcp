"""Typed access to one entity table."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, func, select


class Repository[T: SQLModel]:
    """The queries every entity needs, written once.

    A repository owns no transaction: it reads and stages changes on the
    session it was given, and the unit of work that owns that session commits.
    """

    def __init__(self, session: AsyncSession, model: type[T]) -> None:
        self._session = session
        self._model = model

    async def get(self, id_: Any) -> T | None:
        return await self._session.get(self._model, id_)

    async def by_name(self, name: str) -> T | None:
        """Look up by the entity's natural key; the model must carry a ``name`` column."""
        return await self.one(self._model.name == name)

    async def one(self, *criteria: Any) -> T | None:
        statement = select(self._model).where(*criteria)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def all(self, *criteria: Any, order_by: Sequence[Any] = ()) -> list[T]:
        statement = select(self._model).where(*criteria).order_by(*order_by)
        return list((await self._session.execute(statement)).scalars())

    async def count(self, *criteria: Any) -> int:
        statement = select(func.count()).select_from(
            select(self._model).where(*criteria).subquery()
        )
        return (await self._session.execute(statement)).scalar_one()

    async def page(
        self, *criteria: Any, offset: int, limit: int, order_by: Sequence[Any]
    ) -> tuple[int, list[T]]:
        """One page of results plus the total the page was cut from."""
        total = await self.count(*criteria)
        statement = (
            select(self._model).where(*criteria).order_by(*order_by).offset(offset).limit(limit)
        )
        rows = list((await self._session.execute(statement)).scalars())
        return total, rows

    def add(self, entity: T) -> T:
        self._session.add(entity)
        return entity

    async def delete(self, entity: T) -> None:
        await self._session.delete(entity)
