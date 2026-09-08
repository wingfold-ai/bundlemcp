from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.application.management.audit_filter import AuditFilter
from bundlemcp.domain.audit.audit_record import AuditRecord
from bundlemcp.infrastructure.postgres.rows.audit_record_row import AuditRecordRow
from bundlemcp.infrastructure.postgres.sqlalchemy_repository import SqlAlchemyRepository


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
            order_by=(AuditRecordRow.created_at.desc(), AuditRecordRow.id),  # type: ignore[attr-defined]
        )

    @staticmethod
    def _criteria(filter_: AuditFilter) -> list[ColumnElement[bool]]:
        clauses: list[ColumnElement[bool]] = []
        if filter_.created_from is not None:
            clauses.append(AuditRecordRow.created_at >= filter_.created_from)
        if filter_.created_to is not None:
            clauses.append(AuditRecordRow.created_at <= filter_.created_to)
        if filter_.endpoint_name is not None:
            clauses.append(AuditRecordRow.endpoint_name == filter_.endpoint_name)
        if filter_.bundle_name is not None:
            clauses.append(AuditRecordRow.bundle_name == filter_.bundle_name)
        if filter_.server_name is not None:
            clauses.append(AuditRecordRow.server_name == filter_.server_name)
        if filter_.tool_name is not None:
            clauses.append(
                (AuditRecordRow.tool_name == filter_.tool_name)
                | (AuditRecordRow.presented_tool_name == filter_.tool_name)
            )
        if filter_.user_id is not None:
            clauses.append(AuditRecordRow.user_id == filter_.user_id)
        if filter_.api_key_id is not None:
            clauses.append(AuditRecordRow.api_key_id == filter_.api_key_id)
        if filter_.status is not None:
            clauses.append(AuditRecordRow.status == filter_.status)
        return clauses
