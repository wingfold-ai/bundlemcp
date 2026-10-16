"""Exporting the configuration as a document, and importing one."""

from fastapi import HTTPException, status

from bundlemcp.api.http.management_auth import PrincipalProvider
from bundlemcp.api.http.route import route
from bundlemcp.api.http.service_providers import (
    ConfigExportServiceProvider,
    ConfigImportServiceProvider,
)
from bundlemcp.api.management.controllers.management_controller import ManagementController
from bundlemcp.application.bootstrap.bootstrap_document import BootstrapDocument
from bundlemcp.application.bootstrap.export_document import ExportDocument
from bundlemcp.application.schemas import ImportReport
from bundlemcp.domain.access.principal_kind import PrincipalKind


class ConfigTransferController(ManagementController):
    prefix = ""
    tags = ("config-transfer",)

    @route.get("/export", response_model_exclude_none=True)
    async def export_config(
        self,
        service: ConfigExportServiceProvider,
        principal: PrincipalProvider,
        include_secrets: bool = False,
    ) -> ExportDocument:
        # secret values are a credential: only a person signed in as admin takes them out
        if include_secrets and principal.kind is not PrincipalKind.ADMIN:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "include_secrets needs an admin session; a service key cannot export secret "
                "values (SEC-11)",
            )
        return await service.export(include_secrets=include_secrets, requested_by=principal)

    @route.post("/import")
    async def import_config(
        self, body: BootstrapDocument, service: ConfigImportServiceProvider, dry_run: bool = False
    ) -> ImportReport:
        return await service.run(body, dry_run=dry_run)
