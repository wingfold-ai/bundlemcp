"""Upstream server registry routes, including upstream OAuth client configuration."""

from typing import Annotated

from fastapi import HTTPException, Query, status

from bundlemcp.api.http.management_auth import PrincipalProvider
from bundlemcp.api.http.pagination import PageProvider
from bundlemcp.api.http.route import route
from bundlemcp.api.http.service_providers import (
    ServerInspectionServiceProvider,
    ServerJsonImporterProvider,
    ServerServiceProvider,
    UpstreamOAuthConfigServiceProvider,
)
from bundlemcp.api.management.controllers.management_controller import ManagementController
from bundlemcp.application.schemas import (
    DiscoveryResult,
    Page,
    ServerInspection,
    ServerInspectRequest,
    ServerJsonDraft,
    ServerJsonImport,
    ServerRead,
    ServerUpsert,
    ToolRead,
    UpstreamOAuthClientRead,
    UpstreamOAuthConfig,
    UpstreamOAuthStatusRead,
)
from bundlemcp.domain.access.api_key_scope import ApiKeyScope


class ServerController(ManagementController):
    prefix = "/upstreams"
    tags = ("upstreams",)

    @route.get("", access=ApiKeyScope.READ)
    async def list_servers(
        self, service: ServerServiceProvider, page: PageProvider
    ) -> Page[ServerRead]:
        return await service.list(offset=page.offset, limit=page.limit)

    @route.post(":inspect", access=ApiKeyScope.UPSTREAMS_WRITE)
    async def inspect_server(
        self, body: ServerInspectRequest, service: ServerInspectionServiceProvider
    ) -> ServerInspection:
        """Probe a URL without registering it: what it is and what registering it takes."""
        return await service.inspect(body)

    @route.post(":from-server-json", access=ApiKeyScope.UPSTREAMS_WRITE)
    async def draft_from_server_json(
        self, body: ServerJsonImport, importer: ServerJsonImporterProvider
    ) -> ServerJsonDraft:
        """Draft a registration from an MCP Registry server.json; nothing is stored."""
        return importer.draft(body.document)

    @route.get("/{name}", access=ApiKeyScope.READ)
    async def get_server(self, name: str, service: ServerServiceProvider) -> ServerRead:
        return await service.get(name)

    @route.put("/{name}", access=ApiKeyScope.UPSTREAMS_WRITE)
    async def upsert_server(
        self,
        name: str,
        body: ServerUpsert,
        service: ServerServiceProvider,
        principal: PrincipalProvider,
    ) -> ServerRead:
        if body.name != name:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "body.name must match path name"
            )
        return await service.upsert(body, actor=principal)

    @route.delete(
        "/{name}", status_code=status.HTTP_204_NO_CONTENT, access=ApiKeyScope.UPSTREAMS_WRITE
    )
    async def delete_server(self, name: str, service: ServerServiceProvider) -> None:
        await service.delete(name)

    @route.post("/{name}:rename", access=ApiKeyScope.UPSTREAMS_WRITE)
    async def rename_server(
        self, name: str, new_name: str, service: ServerServiceProvider, force: bool = False
    ) -> ServerRead:
        return await service.rename(name, new_name, force=force)

    @route.get("/{name}/tools", access=ApiKeyScope.READ)
    async def list_tools(
        self, name: str, service: ServerServiceProvider, page: PageProvider
    ) -> Page[ToolRead]:
        return await service.list_tools(name, offset=page.offset, limit=page.limit)

    @route.post("/{name}:refresh-tools", access=ApiKeyScope.UPSTREAMS_WRITE)
    async def refresh_tools(
        self,
        name: str,
        service: ServerServiceProvider,
        prune: Annotated[
            bool,
            Query(
                description="Also delete the tools the upstream no longer lists, with their "
                "curation in every bundle; only done when the probe succeeds"
            ),
        ] = False,
    ) -> DiscoveryResult:
        return await service.refresh_tools(name, prune=prune)

    # --- upstream OAuth client config + status ---

    @route.put("/{name}/upstream-oauth", access=ApiKeyScope.UPSTREAMS_WRITE)
    async def set_upstream_oauth(
        self, name: str, body: UpstreamOAuthConfig, service: UpstreamOAuthConfigServiceProvider
    ) -> UpstreamOAuthClientRead:
        return await service.set_client(name, body)

    @route.get("/{name}/upstream-oauth", access=ApiKeyScope.READ)
    async def upstream_oauth_status(
        self, name: str, service: UpstreamOAuthConfigServiceProvider
    ) -> UpstreamOAuthStatusRead:
        return await service.status(name)

    @route.post("/{name}/upstream-oauth:connect", access=ApiKeyScope.UPSTREAMS_WRITE)
    async def connect_upstream_oauth_client(
        self, name: str, service: UpstreamOAuthConfigServiceProvider
    ) -> UpstreamOAuthStatusRead:
        """Obtain the shared connection of a client-credentials client now."""
        return await service.connect_client(name)

    @route.delete(
        "/{name}/upstream-oauth/token",
        status_code=status.HTTP_204_NO_CONTENT,
        access=ApiKeyScope.UPSTREAMS_WRITE,
    )
    async def disconnect_upstream_oauth(
        self, name: str, service: UpstreamOAuthConfigServiceProvider
    ) -> None:
        await service.disconnect(name)
