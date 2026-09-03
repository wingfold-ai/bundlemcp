"""Audit log routes (read-only)."""

from typing import Annotated

from fastapi import Depends

from bundlemcp.api.controllers.management_controller import ManagementController
from bundlemcp.api.pagination import PageProvider
from bundlemcp.http import route
from bundlemcp.providers import AuditServiceProvider
from bundlemcp.schemas import AuditRecordRead, Page
from bundlemcp.services import AuditFilter

# AUD-6: one query parameter per filter field, parsed straight into the model
AuditFilterQuery = Annotated[AuditFilter, Depends(AuditFilter)]


class AuditController(ManagementController):
    prefix = "/audit-records"
    tags = ("audit",)

    @route.get("")
    async def list_audit_records(
        self, service: AuditServiceProvider, page: PageProvider, filter_: AuditFilterQuery
    ) -> Page[AuditRecordRead]:
        return await service.list(filter_, offset=page.offset, limit=page.limit)
