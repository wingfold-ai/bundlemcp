"""Server registry routes, including upstream OAuth client configuration."""

from fastapi import HTTPException, status

from bundlemcp.api.controllers.management_controller import ManagementController
from bundlemcp.api.pagination import PageProvider
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

    def register(self) -> None:
        self.get("", self.list_servers)
        self.get("/{name}", self.get_server)
        self.put("/{name}", self.upsert_server)
        self.delete("/{name}", self.delete_server, status_code=status.HTTP_204_NO_CONTENT)
        self.post("/{name}:rename", self.rename_server)
        self.get("/{name}/tools", self.list_tools)
        self.post("/{name}:refresh-tools", self.refresh_tools)
        # upstream OAuth client config + status (spec 23, UPO-1/5)
        self.put("/{name}/upstream-oauth", self.set_upstream_oauth)
        self.get("/{name}/upstream-oauth", self.upstream_oauth_status)
        self.delete(
            "/{name}/upstream-oauth/token",
            self.disconnect_upstream_oauth,
            status_code=status.HTTP_204_NO_CONTENT,
        )

    async def list_servers(
        self, service: ServerServiceProvider, page: PageProvider
    ) -> Page[ServerRead]:
        return await service.list(offset=page.offset, limit=page.limit)

    async def get_server(self, name: str, service: ServerServiceProvider) -> ServerRead:
        return await service.get(name)

    async def upsert_server(
        self, name: str, body: ServerUpsert, service: ServerServiceProvider
    ) -> ServerRead:
        if body.name != name:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "body.name must match path name"
            )
        return await service.upsert(body)

    async def delete_server(self, name: str, service: ServerServiceProvider) -> None:
        await service.delete(name)

    async def rename_server(
        self, name: str, new_name: str, service: ServerServiceProvider, force: bool = False
    ) -> ServerRead:
        return await service.rename(name, new_name, force=force)

    async def list_tools(
        self, name: str, service: ServerServiceProvider, page: PageProvider
    ) -> Page[ToolRead]:
        return await service.list_tools(name, offset=page.offset, limit=page.limit)

    async def refresh_tools(self, name: str, service: ServerServiceProvider) -> DiscoveryResult:
        return await service.refresh_tools(name)

    async def set_upstream_oauth(
        self, name: str, body: UpstreamOAuthConfig, service: UpstreamOAuthConfigServiceProvider
    ) -> UpstreamOAuthClientRead:
        return await service.set_client(name, body)

    async def upstream_oauth_status(
        self, name: str, service: UpstreamOAuthConfigServiceProvider
    ) -> UpstreamOAuthStatusRead:
        return await service.status(name)

    async def disconnect_upstream_oauth(
        self, name: str, service: UpstreamOAuthConfigServiceProvider
    ) -> None:
        await service.disconnect(name)
