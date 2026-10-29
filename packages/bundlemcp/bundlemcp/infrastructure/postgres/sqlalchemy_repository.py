"""Typed SQLAlchemy access to one entity table; the base every adapter here builds on."""

from collections.abc import Callable, Sequence
from typing import Any

from pydantic import BaseModel
from sqlalchemy import ColumnElement, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, func, select

from bundlemcp.application.contracts.persistence.page_slice import PageSlice


class SqlAlchemyRepository[TEntity: BaseModel, TRow: SQLModel]:
    """Reads rows and returns entities; stages entities and writes rows.

    The entity is the domain's plain Pydantic model; the row is the SQLModel
    table class. Mapping is generic: a row becomes an entity through
    ``model_validate(row, from_attributes=True)``, an entity becomes a row
    through its ``model_dump``. A repository owns no transaction: ``add`` only
    stages, and the staged entities are merged into the session before the
    next query or the enclosing commit, so a unit of work still sees its own
    writes. The criteria-taking methods are storage vocabulary and stay inside
    this package; each adapter wraps them in a named query.
    """

    def __init__(
        self,
        session: AsyncSession,
        entity: type[TEntity],
        row: type[TRow],
        *,
        key: Callable[[TEntity], Any] = lambda entity: entity.id,  # type: ignore[attr-defined]
    ) -> None:
        self._session = session
        self.entity = entity
        self._row = row
        self._key = key
        self._pending: list[TEntity] = []

    # ---- mapping --------------------------------------------------------------------------

    def _to_entity(self, row: TRow) -> TEntity:
        return self.entity.model_validate(row, from_attributes=True)

    def _to_row(self, entity: TEntity) -> TRow:
        return self._row(**entity.model_dump())

    async def flush_pending(self) -> None:
        """Merge every staged entity into the session, so later reads see it."""
        pending, self._pending = self._pending, []
        for entity in pending:
            await self._session.merge(self._to_row(entity))

    # ---- the port -------------------------------------------------------------------------

    async def get(self, id_: Any) -> TEntity | None:
        await self.flush_pending()
        row = await self._session.get(self._row, id_)
        return self._to_entity(row) if row is not None else None

    async def by_name(self, name: str) -> TEntity | None:
        """Look up by the entity's natural key; the row must carry a ``name`` column."""
        return await self.one(self._row.name == name)  # type: ignore[attr-defined]

    def add(self, entity: TEntity) -> TEntity:
        self._pending.append(entity)
        return entity

    async def delete(self, entity: TEntity) -> None:
        await self.flush_pending()
        row = await self._session.get(self._row, self._key(entity))
        if row is not None:
            await self._session.delete(row)

    async def refresh(self, entity: TEntity) -> None:
        """Copy the stored state back onto the entity, so generated values are present."""
        await self.flush_pending()
        row = await self._session.get(self._row, self._key(entity))
        if row is None:
            return
        await self._session.refresh(row)
        for field, value in self._to_entity(row):
            setattr(entity, field, value)

    # ---- storage vocabulary, wrapped by the adapters ---------------------------------------

    async def one(self, *criteria: ColumnElement[bool]) -> TEntity | None:
        await self.flush_pending()
        statement = select(self._row).where(*criteria)
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return self._to_entity(row) if row is not None else None

    async def all(
        self, *criteria: ColumnElement[bool], order_by: Sequence[Any] = ()
    ) -> list[TEntity]:
        await self.flush_pending()
        statement = select(self._row).where(*criteria).order_by(*order_by)
        return [self._to_entity(r) for r in (await self._session.execute(statement)).scalars()]

    async def count(self, *criteria: ColumnElement[bool]) -> int:
        await self.flush_pending()
        statement = select(func.count()).select_from(select(self._row).where(*criteria).subquery())
        return (await self._session.execute(statement)).scalar_one()

    async def page(
        self, *criteria: ColumnElement[bool], offset: int, limit: int, order_by: Sequence[Any]
    ) -> PageSlice[TEntity]:
        """One page of results plus the total the page was cut from."""
        total = await self.count(*criteria)
        statement = (
            select(self._row).where(*criteria).order_by(*order_by).offset(offset).limit(limit)
        )
        rows = [self._to_entity(r) for r in (await self._session.execute(statement)).scalars()]
        return PageSlice(items=rows, total=total)

    async def delete_where(self, *criteria: ColumnElement[bool]) -> int:
        """Delete every row the criteria match, in one statement; returns how many."""
        await self.flush_pending()
        result = await self._session.execute(delete(self._row).where(*criteria))
        return result.rowcount

    async def update_where(self, *criteria: Any, **values: Any) -> int:
        """Set columns on every row the criteria match, in one statement.

        Returns how many rows changed. A zero when exactly one row was expected
        means another transaction got there first: the statement is the
        compare-and-set that makes a single-use record single-use under
        concurrency, which a read followed by a write cannot be.
        """
        await self.flush_pending()
        statement = (
            update(self._row)
            .where(*criteria)
            .values(**values)
            .execution_options(synchronize_session="fetch")
        )
        result = await self._session.execute(statement)
        return result.rowcount
