"""Read access to the append-only audit log with the standard list filters."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from bundlemcp.models import AuditRecord, AuditStatus
from bundlemcp.schemas import AuditRecordRead, Page
from bundlemcp.store import Repository, UnitOfWork


class AuditFilter(BaseModel):
    """The narrowing a listing of audit records may ask for; every field is optional."""

    created_from: datetime | None = Field(default=None, description="Earliest call time included")
    created_to: datetime | None = Field(default=None, description="Latest call time included")
    endpoint_name: str | None = Field(default=None, description="Only calls on this endpoint")
    bundle_name: str | None = Field(default=None, description="Only calls into this bundle")
    server_name: str | None = Field(default=None, description="Only calls routed to this server")
    tool_name: str | None = Field(
        default=None,
        description="Only calls of this tool, matched by upstream or client-visible name",
    )
    user_id: uuid.UUID | None = Field(default=None, description="Only calls by this user")
    api_key_id: uuid.UUID | None = Field(default=None, description="Only calls with this key")
    status: AuditStatus | None = Field(default=None, description="Only calls with this outcome")

    def criteria(self) -> list[object]:
        clauses: list[object] = []
        if self.created_from is not None:
            clauses.append(AuditRecord.created_at >= self.created_from)
        if self.created_to is not None:
            clauses.append(AuditRecord.created_at <= self.created_to)
        if self.endpoint_name is not None:
            clauses.append(AuditRecord.endpoint_name == self.endpoint_name)
        if self.bundle_name is not None:
            clauses.append(AuditRecord.bundle_name == self.bundle_name)
        if self.server_name is not None:
            clauses.append(AuditRecord.server_name == self.server_name)
        if self.tool_name is not None:
            clauses.append(
                (AuditRecord.tool_name == self.tool_name)
                | (AuditRecord.presented_tool_name == self.tool_name)
            )
        if self.user_id is not None:
            clauses.append(AuditRecord.user_id == self.user_id)
        if self.api_key_id is not None:
            clauses.append(AuditRecord.api_key_id == self.api_key_id)
        if self.status is not None:
            clauses.append(AuditRecord.status == self.status)
        return clauses


class AuditService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._records = Repository(uow.session, AuditRecord)

    async def list(self, filter_: AuditFilter, *, offset: int, limit: int) -> Page[AuditRecordRead]:
        total, rows = await self._records.page(
            *filter_.criteria(),
            offset=offset,
            limit=limit,
            order_by=(AuditRecord.created_at.desc(), AuditRecord.id),  # type: ignore[attr-defined]
        )
        return Page(
            items=[AuditRecordRead.from_entity(r) for r in rows],
            total=total,
            offset=offset,
            limit=limit,
        )
