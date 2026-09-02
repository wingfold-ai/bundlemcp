"""Audit log routes (read-only).

Thin controllers: HTTP concerns only; business logic lives in AuditService.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter

from bundlemcp.api.auth import ServiceAuthProvider
from bundlemcp.api.pagination import PageProvider
from bundlemcp.api.providers import AuditServiceProvider
from bundlemcp.schemas import AuditRecordRead, Page

router = APIRouter(prefix="/audit-records", tags=["audit"])


@router.get("")
async def list_audit_records(  # noqa: PLR0913 - one query param per AUD-6 filter
    service: AuditServiceProvider,
    _auth: ServiceAuthProvider,
    page: PageProvider,
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
    return await service.list(
        offset=page.offset,
        limit=page.limit,
        created_from=created_from,
        created_to=created_to,
        endpoint_name=endpoint_name,
        bundle_name=bundle_name,
        server_name=server_name,
        tool_name=tool_name,
        user_id=user_id,
        api_key_id=api_key_id,
        status=status,
    )
