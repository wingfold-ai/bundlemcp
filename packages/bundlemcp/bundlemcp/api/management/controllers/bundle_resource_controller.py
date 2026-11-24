"""Routes for the documents a bundle itself serves."""

from fastapi import HTTPException, status

from bundlemcp.api.http.pagination import PageProvider
from bundlemcp.api.http.route import route
from bundlemcp.api.http.service_providers import BundleResourceServiceProvider
from bundlemcp.api.management.controllers.management_controller import ManagementController
from bundlemcp.application.schemas import BundleResourceRead, BundleResourceUpsert, Page
from bundlemcp.domain.access.api_key_scope import ApiKeyScope


class BundleResourceController(ManagementController):
    # `{name:path}` because a resource name may contain '/' folders
    prefix = "/bundles/{bundle}/resources"
    tags = ("bundles",)

    @route.get("", access=ApiKeyScope.READ)
    async def list_resources(
        self, bundle: str, service: BundleResourceServiceProvider, page: PageProvider
    ) -> Page[BundleResourceRead]:
        return await service.list(bundle, offset=page.offset, limit=page.limit)

    @route.get("/{name:path}", access=ApiKeyScope.READ)
    async def get_resource(
        self, bundle: str, name: str, service: BundleResourceServiceProvider
    ) -> BundleResourceRead:
        return await service.get(bundle, name)

    @route.put("/{name:path}", access=ApiKeyScope.BUNDLES_WRITE)
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

    @route.delete(
        "/{name:path}", status_code=status.HTTP_204_NO_CONTENT, access=ApiKeyScope.BUNDLES_WRITE
    )
    async def delete_resource(
        self, bundle: str, name: str, service: BundleResourceServiceProvider
    ) -> None:
        await service.delete(bundle, name)
