"""Audit log routes (read-only)."""

from typing import Annotated

from fastapi import Depends

from bundlemcp.api.http.pagination import PageProvider
from bundlemcp.api.http.route import route
from bundlemcp.api.http.service_providers import AuditServiceProvider
from bundlemcp.api.management.controllers.management_controller import ManagementController
from bundlemcp.application.management.audit_service import AuditFilter
from bundlemcp.application.schemas import AuditRecordRead, Page

# one query parameter per filter field, parsed straight into the model
AuditFilterQuery = Annotated[AuditFilter, Depends(AuditFilter)]


class AuditController(ManagementController):
    prefix = "/audit-records"
    tags = ("audit",)

    @route.get("")
    async def list_audit_records(
        self, service: AuditServiceProvider, page: PageProvider, filter_: AuditFilterQuery
    ) -> Page[AuditRecordRead]:
        return await service.list(filter_, offset=page.offset, limit=page.limit)
