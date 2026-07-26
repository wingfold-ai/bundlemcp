"""Read access to the append-only audit log with the standard list filters."""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from bundlemcp.models import AuditRecord
from bundlemcp.schemas import AuditRecordRead, Page


class AuditService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list(
        self,
        *,
        offset: int,
        limit: int,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        endpoint_name: str | None = None,
        bundle_name: str | None = None,
        server_name: str | None = None,
        tool_name: str | None = None,
        user_id: uuid.UUID | None = None,
        api_key_id: uuid.UUID | None = None,
        status: str | None = None,
    ) -> Page[AuditRecordRead]:
        query = select(AuditRecord)
        if created_from is not None:
            query = query.where(AuditRecord.created_at >= created_from)
        if created_to is not None:
            query = query.where(AuditRecord.created_at <= created_to)
        if endpoint_name is not None:
            query = query.where(AuditRecord.endpoint_name == endpoint_name)
        if bundle_name is not None:
            query = query.where(AuditRecord.bundle_name == bundle_name)
        if server_name is not None:
            query = query.where(AuditRecord.server_name == server_name)
        if tool_name is not None:
            # matches either the upstream or the client-visible name
            query = query.where(
                (AuditRecord.tool_name == tool_name)
                | (AuditRecord.presented_tool_name == tool_name)
            )
        if user_id is not None:
            query = query.where(AuditRecord.user_id == user_id)
        if api_key_id is not None:
            query = query.where(AuditRecord.api_key_id == api_key_id)
        if status is not None:
            query = query.where(AuditRecord.status == status)

        total = (
            await self._db.execute(select(func.count()).select_from(query.subquery()))
        ).scalar_one()
        rows = (
            await self._db.execute(
                query.order_by(AuditRecord.created_at.desc(), AuditRecord.id)
                .offset(offset)
                .limit(limit)
            )
        ).scalars()
        return Page(
            items=[AuditRecordRead.model_validate(r) for r in rows],
            total=total,
            offset=offset,
            limit=limit,
        )
