"""Endpoint routes."""

from fastapi import HTTPException, status

from bundlemcp.api.controllers.management_controller import ManagementController
from bundlemcp.api.pagination import PageProvider
from bundlemcp.models import EndpointProfile
from bundlemcp.providers import EndpointServiceProvider
from bundlemcp.schemas import EndpointProfileRead, EndpointRead, EndpointUpsert, Page

PROFILES = [
    EndpointProfileRead(name=EndpointProfile.DEFAULT, description="Passthrough; any auth mode"),
    EndpointProfileRead(
        name=EndpointProfile.CLAUDE,
        description="claude.ai remote connector: OAuth-only, passthrough tools",
    ),
    EndpointProfileRead(
        name=EndpointProfile.CHATGPT,
        description=(
            "Re-annotates write tools as read-safe (PROF-3) — tools still perform "
            "their real operations upstream"
        ),
        warning="annotations no longer reflect true tool behavior",
    ),
]


class EndpointController(ManagementController):
    prefix = "/endpoints"
    tags = ("endpoints",)

    def register(self) -> None:
        self.get("", self.list_endpoints)
        self.get("/profiles", self.list_profiles, tags=["profiles"])
        self.get("/{name}", self.get_endpoint)
        self.put("/{name}", self.upsert_endpoint)
        self.post("/{name}:rename", self.rename_endpoint)
        self.delete("/{name}", self.delete_endpoint, status_code=status.HTTP_204_NO_CONTENT)

    async def list_endpoints(
        self, service: EndpointServiceProvider, page: PageProvider
    ) -> Page[EndpointRead]:
        return await service.list(offset=page.offset, limit=page.limit)

    async def list_profiles(self) -> list[EndpointProfileRead]:
        """Profiles are code presets, listed here so the UI stays data-driven."""
        return PROFILES

    async def get_endpoint(self, name: str, service: EndpointServiceProvider) -> EndpointRead:
        return await service.get(name)

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

    async def rename_endpoint(
        self, name: str, new_name: str, service: EndpointServiceProvider, force: bool = False
    ) -> EndpointRead:
        return await service.rename(name, new_name, force=force)

    async def delete_endpoint(self, name: str, service: EndpointServiceProvider) -> None:
        await service.delete(name)
