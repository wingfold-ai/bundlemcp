from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from bundlemcp.application.management.audit_cursor import AuditCursor
from bundlemcp.application.management.audit_filter import AuditFilter
from bundlemcp.domain.audit.audit_record import AuditRecord
from bundlemcp.infrastructure.postgres.rows.audit_record_row import AuditRecordRow
from bundlemcp.infrastructure.postgres.sqlalchemy_repository import SqlAlchemyRepository

_EQUALS: dict[str, InstrumentedAttribute[Any]] = {
    "kind": AuditRecordRow.kind,  # type: ignore[dict-item]
    "endpoint_name": AuditRecordRow.endpoint_name,  # type: ignore[dict-item]
    "bundle_name": AuditRecordRow.bundle_name,  # type: ignore[dict-item]
    "server_name": AuditRecordRow.server_name,  # type: ignore[dict-item]
    "user_id": AuditRecordRow.user_id,  # type: ignore[dict-item]
    "api_key_id": AuditRecordRow.api_key_id,  # type: ignore[dict-item]
    "status": AuditRecordRow.status,  # type: ignore[dict-item]
    "idempotency_key": AuditRecordRow.idempotency_key,  # type: ignore[dict-item]
}
"""The filter fields that must equal one column, keyed by filter field name.

The time range and the tool narrowing, which matches either of two columns, are built
beside this table in ``_criteria``.
"""


class SqlAlchemyAuditRepository(SqlAlchemyRepository[AuditRecord, AuditRecordRow]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AuditRecord, AuditRecordRow)

    async def page(
        self, filter_: AuditFilter, *, offset: int, limit: int
    ) -> tuple[int, list[AuditRecord]]:
        return await super().page(
            *self._criteria(filter_),
            offset=offset,
            limit=limit,
            order_by=(AuditRecordRow.created_at.desc(), AuditRecordRow.id.desc()),  # type: ignore[attr-defined]
        )

    async def page_after(
        self, filter_: AuditFilter, *, cursor: AuditCursor | None, limit: int
    ) -> list[AuditRecord]:
        criteria = self._criteria(filter_)
        if cursor is not None:
            criteria.append(
                (AuditRecordRow.created_at < cursor.created_at)
                | (
                    (AuditRecordRow.created_at == cursor.created_at)
                    & (AuditRecordRow.id < cursor.id)  # type: ignore[operator]
                )
            )
        statement = (
            select(AuditRecordRow)
            .where(*criteria)
            .order_by(AuditRecordRow.created_at.desc(), AuditRecordRow.id.desc())  # type: ignore[attr-defined]
            .limit(limit)
        )
        return [self._to_entity(row) for row in (await self._session.execute(statement)).scalars()]

    async def delete_older_than(self, cutoff: datetime, *, limit: int) -> int:
        oldest = (
            select(AuditRecordRow.id)
            .where(AuditRecordRow.created_at < cutoff)
            .limit(limit)
            .scalar_subquery()
        )
        result = await self._session.execute(
            delete(AuditRecordRow).where(AuditRecordRow.id.in_(oldest))  # type: ignore[attr-defined]
        )
        return int(result.rowcount or 0)

    @staticmethod
    def _criteria(filter_: AuditFilter) -> list[ColumnElement[bool]]:
        clauses: list[ColumnElement[bool]] = [
            column == getattr(filter_, field)
            for field, column in _EQUALS.items()
            if getattr(filter_, field) is not None
        ]
        if filter_.created_from is not None:
            clauses.append(AuditRecordRow.created_at >= filter_.created_from)
        if filter_.created_to is not None:
            clauses.append(AuditRecordRow.created_at <= filter_.created_to)
        if filter_.tool_name is not None:
            clauses.append(
                (AuditRecordRow.tool_name == filter_.tool_name)
                | (AuditRecordRow.presented_tool_name == filter_.tool_name)
            )
        return clauses
