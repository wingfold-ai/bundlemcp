"""Upstream server registry routes, including upstream OAuth client configuration."""

from fastapi import HTTPException, status

from bundlemcp.api.http.pagination import PageProvider
from bundlemcp.api.http.route import route
from bundlemcp.api.http.service_providers import (
    ServerInspectionServiceProvider,
    ServerJsonImporterProvider,
    ServerServiceProvider,
    UpstreamOAuthConfigServiceProvider,
)
from bundlemcp.api.management.controllers.management_controller import ManagementController
from bundlemcp.api.management.upstreams_rename import UPSTREAMS_RENAME
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


class ServerController(ManagementController):
    prefix = "/upstreams"
    tags = ("upstreams",)
    former_prefix = "/servers"  # SRV-16: every route also answers at its old path
    deprecation = UPSTREAMS_RENAME

    @route.get("")
    async def list_servers(
        self, service: ServerServiceProvider, page: PageProvider
    ) -> Page[ServerRead]:
        return await service.list(offset=page.offset, limit=page.limit)

    @route.post(":inspect")
    async def inspect_server(
        self, body: ServerInspectRequest, service: ServerInspectionServiceProvider
    ) -> ServerInspection:
        """Probe a URL without registering it: what it is and what registering it takes."""
        return await service.inspect(body)

    @route.post(":from-server-json")
    async def draft_from_server_json(
        self, body: ServerJsonImport, importer: ServerJsonImporterProvider
    ) -> ServerJsonDraft:
        """Draft a registration from an MCP Registry server.json; nothing is stored."""
        return importer.draft(body.document)

    @route.get("/{name}")
    async def get_server(self, name: str, service: ServerServiceProvider) -> ServerRead:
        return await service.get(name)

    @route.put("/{name}")
    async def upsert_server(
        self, name: str, body: ServerUpsert, service: ServerServiceProvider
    ) -> ServerRead:
        if body.name != name:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "body.name must match path name"
            )
        return await service.upsert(body)

    @route.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_server(self, name: str, service: ServerServiceProvider) -> None:
        await service.delete(name)

    @route.post("/{name}:rename")
    async def rename_server(
        self, name: str, new_name: str, service: ServerServiceProvider, force: bool = False
    ) -> ServerRead:
        return await service.rename(name, new_name, force=force)

    @route.get("/{name}/tools")
    async def list_tools(
        self, name: str, service: ServerServiceProvider, page: PageProvider
    ) -> Page[ToolRead]:
        return await service.list_tools(name, offset=page.offset, limit=page.limit)

    @route.post("/{name}:refresh-tools")
    async def refresh_tools(self, name: str, service: ServerServiceProvider) -> DiscoveryResult:
        return await service.refresh_tools(name)

    # --- upstream OAuth client config + status (spec 23, UPO-1/5) ---

    @route.put("/{name}/upstream-oauth")
    async def set_upstream_oauth(
        self, name: str, body: UpstreamOAuthConfig, service: UpstreamOAuthConfigServiceProvider
    ) -> UpstreamOAuthClientRead:
        return await service.set_client(name, body)

    @route.get("/{name}/upstream-oauth")
    async def upstream_oauth_status(
        self, name: str, service: UpstreamOAuthConfigServiceProvider
    ) -> UpstreamOAuthStatusRead:
        return await service.status(name)

    @route.post("/{name}/upstream-oauth:connect")
    async def connect_upstream_oauth_client(
        self, name: str, service: UpstreamOAuthConfigServiceProvider
    ) -> UpstreamOAuthStatusRead:
        """Obtain the shared connection of a client-credentials client now."""
        return await service.connect_client(name)

    @route.delete("/{name}/upstream-oauth/token", status_code=status.HTTP_204_NO_CONTENT)
    async def disconnect_upstream_oauth(
        self, name: str, service: UpstreamOAuthConfigServiceProvider
    ) -> None:
        await service.disconnect(name)
