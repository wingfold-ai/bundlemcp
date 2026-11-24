"""Bundle composition + tool curation routes."""

import uuid

from fastapi import HTTPException, status

from bundlemcp.api.http.pagination import PageProvider
from bundlemcp.api.http.route import route
from bundlemcp.api.http.service_providers import BundleServiceProvider
from bundlemcp.api.management.controllers.management_controller import ManagementController
from bundlemcp.application.schemas import (
    BundleMemberOrder,
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
from bundlemcp.domain.access.api_key_scope import ApiKeyScope


class BundleController(ManagementController):
    prefix = "/bundles"
    tags = ("bundles",)

    @route.get("", access=ApiKeyScope.READ)
    async def list_bundles(
        self, service: BundleServiceProvider, page: PageProvider
    ) -> Page[BundleRead]:
        return await service.list(offset=page.offset, limit=page.limit)

    @route.put("/{name}", access=ApiKeyScope.BUNDLES_WRITE)
    async def upsert_bundle(
        self, name: str, body: BundleUpsert, service: BundleServiceProvider
    ) -> BundleRead:
        if body.name != name:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "body.name must match path name"
            )
        return await service.upsert(body)

    @route.post("/{name}:rename", access=ApiKeyScope.BUNDLES_WRITE)
    async def rename_bundle(
        self, name: str, new_name: str, service: BundleServiceProvider, force: bool = False
    ) -> BundleRead:
        return await service.rename(name, new_name, force=force)

    @route.get("/{name}", access=ApiKeyScope.READ)
    async def get_bundle(self, name: str, service: BundleServiceProvider) -> BundleRead:
        return await service.get(name)

    @route.delete(
        "/{name}", status_code=status.HTTP_204_NO_CONTENT, access=ApiKeyScope.BUNDLES_WRITE
    )
    async def delete_bundle(self, name: str, service: BundleServiceProvider) -> None:
        await service.delete(name)

    @route.get("/{name}/upstreams", access=ApiKeyScope.READ)
    async def list_members(
        self, name: str, service: BundleServiceProvider
    ) -> list[BundleMemberRead]:
        return await service.list_members(name)

    @route.put("/{name}/upstreams:order", access=ApiKeyScope.BUNDLES_WRITE)
    async def order_members(
        self, name: str, body: BundleMemberOrder, service: BundleServiceProvider
    ) -> list[BundleMemberRead]:
        """Set the order of the bundle's members; the first answers first where several could."""
        return await service.order_members(name, body)

    @route.get("/{name}/tools", access=ApiKeyScope.READ)
    async def list_tools(self, name: str, service: BundleServiceProvider) -> list[BundleToolRead]:
        return await service.list_tools(name)

    @route.put("/{name}/upstreams/{upstream_name}", access=ApiKeyScope.BUNDLES_WRITE)
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
        status_code=status.HTTP_204_NO_CONTENT,
        access=ApiKeyScope.BUNDLES_WRITE,
    )
    async def remove_member(
        self, name: str, upstream_name: str, service: BundleServiceProvider
    ) -> None:
        await service.remove_member(name, upstream_name)

    @route.put("/{name}/tools/{tool_id}", access=ApiKeyScope.BUNDLES_WRITE)
    async def curate_tool(
        self,
        name: str,
        tool_id: uuid.UUID,
        body: BundleToolUpdate,
        service: BundleServiceProvider,
    ) -> ToolCurationRead:
        return await service.curate_tool(name, tool_id, body)
