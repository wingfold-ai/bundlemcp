"""Endpoint routes."""

from fastapi import HTTPException, status

from bundlemcp.api.http.pagination import PageProvider
from bundlemcp.api.http.route import route
from bundlemcp.api.http.service_providers import EndpointServiceProvider
from bundlemcp.api.management.controllers.management_controller import ManagementController
from bundlemcp.application.schemas import EndpointProfileRead, EndpointRead, EndpointUpsert, Page
from bundlemcp.domain.endpoints.endpoint_profile import EndpointProfile

PROFILES = [
    EndpointProfileRead(name=EndpointProfile.DEFAULT, description="Passthrough; any auth mode"),
    EndpointProfileRead(
        name=EndpointProfile.CLAUDE,
        description="claude.ai remote connector: OAuth-only, passthrough tools",
    ),
    EndpointProfileRead(
        name=EndpointProfile.CHATGPT,
        description=(  # PROF-3
            "Re-annotates write tools as read-safe — tools still perform "
            "their real operations upstream"
        ),
        warning="annotations no longer reflect true tool behavior",
    ),
]


class EndpointController(ManagementController):
    prefix = "/endpoints"
    tags = ("endpoints",)

    @route.get("")
    async def list_endpoints(
        self, service: EndpointServiceProvider, page: PageProvider
    ) -> Page[EndpointRead]:
        return await service.list(offset=page.offset, limit=page.limit)

    # declared before /{name}: a literal path must bind ahead of the parameterised one
    @route.get("/profiles", tags=["profiles"])
    async def list_profiles(self) -> list[EndpointProfileRead]:
        """Profiles are code presets, listed here so the UI stays data-driven."""
        return PROFILES

    @route.get("/{name}")
    async def get_endpoint(self, name: str, service: EndpointServiceProvider) -> EndpointRead:
        return await service.get(name)

    @route.put("/{name}")
    async def upsert_endpoint(
        self, name: str, body: EndpointUpsert, service: EndpointServiceProvider
    ) -> EndpointRead:
        if body.name != name:
            # EP-8: changing the public URL needs an explicit rename with force
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "body.name must match path name; rename via :rename with force (EP-8)",
            )
        return await service.upsert(body)

    @route.post("/{name}:rename")
    async def rename_endpoint(
        self, name: str, new_name: str, service: EndpointServiceProvider, force: bool = False
    ) -> EndpointRead:
        return await service.rename(name, new_name, force=force)

    @route.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_endpoint(self, name: str, service: EndpointServiceProvider) -> None:
        await service.delete(name)
