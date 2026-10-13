"""Routes for the documents a bundle itself serves."""

from fastapi import HTTPException, status

from bundlemcp.api.http.pagination import PageProvider
from bundlemcp.api.http.route import route
from bundlemcp.api.http.service_providers import BundleResourceServiceProvider
from bundlemcp.api.management.controllers.management_controller import ManagementController
from bundlemcp.application.schemas import BundleResourceRead, BundleResourceUpsert, Page


class BundleResourceController(ManagementController):
    # BND-31; `{name:path}` because a resource name may contain '/' folders (BND-23)
    prefix = "/bundles/{bundle}/resources"
    tags = ("bundles",)

    @route.get("")
    async def list_resources(
        self, bundle: str, service: BundleResourceServiceProvider, page: PageProvider
    ) -> Page[BundleResourceRead]:
        return await service.list(bundle, offset=page.offset, limit=page.limit)

    @route.get("/{name:path}")
    async def get_resource(
        self, bundle: str, name: str, service: BundleResourceServiceProvider
    ) -> BundleResourceRead:
        return await service.get(bundle, name)

    @route.put("/{name:path}")
    async def upsert_resource(
        self,
        bundle: str,
        name: str,
        body: BundleResourceUpsert,
        service: BundleResourceServiceProvider,
    ) -> BundleResourceRead:
        if body.name != name:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "body.name must match path name"
            )
        return await service.upsert(bundle, body)

    @route.delete("/{name:path}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_resource(
        self, bundle: str, name: str, service: BundleResourceServiceProvider
    ) -> None:
        await service.delete(bundle, name)
