"""Bundle composition + tool curation routes."""

import uuid

from fastapi import HTTPException, status

from bundlemcp.api.http.pagination import PageProvider
from bundlemcp.api.http.route import route
from bundlemcp.api.http.service_providers import BundleServiceProvider
from bundlemcp.api.management.controllers.management_controller import ManagementController
from bundlemcp.api.management.upstreams_rename import UPSTREAMS_RENAME
from bundlemcp.application.schemas import (
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
    deprecation = UPSTREAMS_RENAME  # SRV-16: members moved from /servers to /upstreams

    @route.get("")
    async def list_bundles(
        self, service: BundleServiceProvider, page: PageProvider
    ) -> Page[BundleRead]:
        return await service.list(offset=page.offset, limit=page.limit)

    @route.put("/{name}")
    async def upsert_bundle(
        self, name: str, body: BundleUpsert, service: BundleServiceProvider
    ) -> BundleRead:
        if body.name != name:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "body.name must match path name"
            )
        return await service.upsert(body)

    @route.get("/{name}")
    async def get_bundle(self, name: str, service: BundleServiceProvider) -> BundleRead:
        return await service.get(name)

    @route.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_bundle(self, name: str, service: BundleServiceProvider) -> None:
        await service.delete(name)

    @route.get("/{name}/upstreams", former_path="/{name}/servers")
    async def list_members(
        self, name: str, service: BundleServiceProvider
    ) -> list[BundleMemberRead]:
        return await service.list_members(name)

    @route.get("/{name}/tools")
    async def list_tools(self, name: str, service: BundleServiceProvider) -> list[BundleToolRead]:
        return await service.list_tools(name)

    @route.put("/{name}/upstreams/{upstream_name}", former_path="/{name}/servers/{upstream_name}")
    async def set_member(
        self,
        name: str,
        upstream_name: str,
        body: BundleServerUpdate,
        service: BundleServiceProvider,
    ) -> BundleMembershipRead:
        return await service.set_member(name, upstream_name, body)

    @route.delete(
        "/{name}/upstreams/{upstream_name}",
        former_path="/{name}/servers/{upstream_name}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def remove_member(
        self, name: str, upstream_name: str, service: BundleServiceProvider
    ) -> None:
        await service.remove_member(name, upstream_name)

    @route.put("/{name}/tools/{tool_id}")
    async def curate_tool(
        self,
        name: str,
        tool_id: uuid.UUID,
        body: BundleToolUpdate,
        service: BundleServiceProvider,
    ) -> ToolCurationRead:
        return await service.curate_tool(name, tool_id, body)
