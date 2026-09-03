"""Bundle composition + tool curation routes."""

import uuid

from fastapi import HTTPException, status

from bundlemcp.api.controllers.management_controller import ManagementController
from bundlemcp.api.pagination import PageProvider
from bundlemcp.providers import BundleServiceProvider
from bundlemcp.schemas import (
    BundleMemberRead,
    BundleMembershipRead,
    BundleRead,
    BundleServerUpdate,
    BundleToolRead,
    BundleToolUpdate,
    BundleUpsert,
    Page,
    ToolCurationRead,
)


class BundleController(ManagementController):
    prefix = "/bundles"
    tags = ("bundles",)

    def register(self) -> None:
        self.get("", self.list_bundles)
        self.put("/{name}", self.upsert_bundle)
        self.get("/{name}", self.get_bundle)
        self.delete("/{name}", self.delete_bundle, status_code=status.HTTP_204_NO_CONTENT)
        self.get("/{name}/servers", self.list_members)
        self.get("/{name}/tools", self.list_tools)
        self.put("/{name}/servers/{server_name}", self.set_member)
        self.delete(
            "/{name}/servers/{server_name}",
            self.remove_member,
            status_code=status.HTTP_204_NO_CONTENT,
        )
        self.put("/{name}/tools/{tool_id}", self.curate_tool)

    async def list_bundles(
        self, service: BundleServiceProvider, page: PageProvider
    ) -> Page[BundleRead]:
        return await service.list(offset=page.offset, limit=page.limit)

    async def upsert_bundle(
        self, name: str, body: BundleUpsert, service: BundleServiceProvider
    ) -> BundleRead:
        if body.name != name:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "body.name must match path name"
            )
        return await service.upsert(body)

    async def get_bundle(self, name: str, service: BundleServiceProvider) -> BundleRead:
        return await service.get(name)

    async def delete_bundle(self, name: str, service: BundleServiceProvider) -> None:
        await service.delete(name)

    async def list_members(
        self, name: str, service: BundleServiceProvider
    ) -> list[BundleMemberRead]:
        return await service.list_members(name)

    async def list_tools(self, name: str, service: BundleServiceProvider) -> list[BundleToolRead]:
        return await service.list_tools(name)

    async def set_member(
        self,
        name: str,
        server_name: str,
        body: BundleServerUpdate,
        service: BundleServiceProvider,
    ) -> BundleMembershipRead:
        return await service.set_member(name, server_name, body)

    async def remove_member(
        self, name: str, server_name: str, service: BundleServiceProvider
    ) -> None:
        await service.remove_member(name, server_name)

    async def curate_tool(
        self,
        name: str,
        tool_id: uuid.UUID,
        body: BundleToolUpdate,
        service: BundleServiceProvider,
    ) -> ToolCurationRead:
        return await service.curate_tool(name, tool_id, body)
