"""Routes for the prompts a bundle itself serves."""

from fastapi import HTTPException, status

from bundlemcp.api.http.pagination import PageProvider
from bundlemcp.api.http.route import route
from bundlemcp.api.http.service_providers import BundlePromptServiceProvider
from bundlemcp.api.management.controllers.management_controller import ManagementController
from bundlemcp.application.schemas import BundlePromptRead, BundlePromptUpsert, Page


class BundlePromptController(ManagementController):
    prefix = "/bundles/{bundle}/prompts"
    tags = ("bundles",)

    @route.get("")
    async def list_prompts(
        self, bundle: str, service: BundlePromptServiceProvider, page: PageProvider
    ) -> Page[BundlePromptRead]:
        return await service.list(bundle, offset=page.offset, limit=page.limit)

    @route.get("/{name}")
    async def get_prompt(
        self, bundle: str, name: str, service: BundlePromptServiceProvider
    ) -> BundlePromptRead:
        return await service.get(bundle, name)

    @route.put("/{name}")
    async def upsert_prompt(
        self, bundle: str, name: str, body: BundlePromptUpsert, service: BundlePromptServiceProvider
    ) -> BundlePromptRead:
        if body.name != name:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "body.name must match path name"
            )
        return await service.upsert(bundle, body)

    @route.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_prompt(
        self, bundle: str, name: str, service: BundlePromptServiceProvider
    ) -> None:
        await service.delete(bundle, name)
