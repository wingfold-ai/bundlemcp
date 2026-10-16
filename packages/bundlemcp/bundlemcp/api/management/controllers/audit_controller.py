"""Audit log routes (read-only)."""

import csv
import io
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from fastapi.responses import StreamingResponse

from bundlemcp.api.http.pagination import PageProvider
from bundlemcp.api.http.route import route
from bundlemcp.api.http.service_providers import (
    AuditExportServiceProvider,
    AuditServiceProvider,
)
from bundlemcp.api.management.controllers.management_controller import ManagementController
from bundlemcp.application.management.audit_service import AuditFilter
from bundlemcp.application.schemas import AuditRecordRead, Page

# one query parameter per filter field, parsed straight into the model
AuditFilterQuery = Annotated[AuditFilter, Depends(AuditFilter)]
EXPORT_COLUMNS = tuple(AuditRecordRead.model_fields)


async def _csv(records: AsyncIterator[AuditRecordRead]) -> AsyncIterator[str]:
    """A header, then one row per record, every field of the read model."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    yield buffer.getvalue()
    async for record in records:
        buffer.seek(0)
        buffer.truncate()
        writer.writerow(record.model_dump(mode="json"))
        yield buffer.getvalue()


class AuditController(ManagementController):
    prefix = "/audit-records"
    tags = ("audit",)

    @route.get(":export", response_class=StreamingResponse)
    async def export_audit_records(
        self, service: AuditExportServiceProvider, filter_: AuditFilterQuery
    ) -> StreamingResponse:
        """Every record the filters match, newest first, as CSV; the list's filters, no paging."""
        return StreamingResponse(
            _csv(service.records(filter_)),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="audit-records.csv"'},
        )

    @route.get("")
    async def list_audit_records(
        self, service: AuditServiceProvider, page: PageProvider, filter_: AuditFilterQuery
    ) -> Page[AuditRecordRead]:
        return await service.list(filter_, offset=page.offset, limit=page.limit)
