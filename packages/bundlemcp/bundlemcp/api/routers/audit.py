"""Audit log routes (read-only).

Thin controllers: HTTP concerns only; business logic lives in AuditService.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from bundlemcp.api.auth import ServiceAuthProvider
from bundlemcp.api.pagination import PageProvider
from bundlemcp.providers import AuditServiceProvider
from bundlemcp.schemas import AuditRecordRead, Page
from bundlemcp.services import AuditFilter

router = APIRouter(prefix="/audit-records", tags=["audit"])

# AUD-6: one query parameter per filter field, parsed straight into the model
AuditFilterQuery = Annotated[AuditFilter, Depends(AuditFilter)]


@router.get("")
async def list_audit_records(
    service: AuditServiceProvider,
    _auth: ServiceAuthProvider,
    page: PageProvider,
    filter_: AuditFilterQuery,
) -> Page[AuditRecordRead]:
    return await service.list(filter_, offset=page.offset, limit=page.limit)
