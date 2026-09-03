"""Server registry routes, including upstream OAuth client configuration."""

from fastapi import HTTPException, status

from bundlemcp.api.controllers.management_controller import ManagementController
from bundlemcp.api.pagination import PageProvider
from bundlemcp.http import route
from bundlemcp.providers import ServerServiceProvider, UpstreamOAuthConfigServiceProvider
from bundlemcp.schemas import (
    DiscoveryResult,
    Page,
    ServerRead,
    ServerUpsert,
    ToolRead,
    UpstreamOAuthClientRead,
    UpstreamOAuthConfig,
    UpstreamOAuthStatusRead,
)


class ServerController(ManagementController):
    prefix = "/servers"
    tags = ("servers",)

    @route.get("")
    async def list_servers(
        self, service: ServerServiceProvider, page: PageProvider
    ) -> Page[ServerRead]:
        return await service.list(offset=page.offset, limit=page.limit)

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

    @route.delete("/{name}/upstream-oauth/token", status_code=status.HTTP_204_NO_CONTENT)
    async def disconnect_upstream_oauth(
        self, name: str, service: UpstreamOAuthConfigServiceProvider
    ) -> None:
        await service.disconnect(name)
