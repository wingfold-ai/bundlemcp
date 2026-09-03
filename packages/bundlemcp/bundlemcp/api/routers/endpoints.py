"""Endpoint routes.

Thin controllers: HTTP concerns only; business logic lives in EndpointService.
"""

from fastapi import APIRouter, HTTPException, status

from bundlemcp.api.auth import ServiceAuthProvider
from bundlemcp.api.pagination import PageProvider
from bundlemcp.models import EndpointProfile
from bundlemcp.providers import EndpointServiceProvider
from bundlemcp.schemas import EndpointProfileRead, EndpointRead, EndpointUpsert, Page

router = APIRouter(prefix="/endpoints", tags=["endpoints"])


@router.get("")
async def list_endpoints(
    service: EndpointServiceProvider, _auth: ServiceAuthProvider, page: PageProvider
) -> Page[EndpointRead]:
    return await service.list(offset=page.offset, limit=page.limit)


@router.get("/profiles", tags=["profiles"])
async def list_profiles(_auth: ServiceAuthProvider) -> list[EndpointProfileRead]:
    """Profiles are code presets, listed here so the UI stays data-driven."""
    return [
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


@router.get("/{name}")
async def get_endpoint(
    name: str, service: EndpointServiceProvider, _auth: ServiceAuthProvider
) -> EndpointRead:
    return await service.get(name)


@router.put("/{name}")
async def upsert_endpoint(
    name: str, body: EndpointUpsert, service: EndpointServiceProvider, _auth: ServiceAuthProvider
) -> EndpointRead:
    if body.name != name:
        # EP-8: changing the public URL needs an explicit rename with force
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "body.name must match path name; rename via :rename with force (EP-8)",
        )
    return await service.upsert(body)


@router.post("/{name}:rename")
async def rename_endpoint(
    name: str,
    new_name: str,
    service: EndpointServiceProvider,
    _auth: ServiceAuthProvider,
    force: bool = False,
) -> EndpointRead:
    return await service.rename(name, new_name, force=force)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_endpoint(
    name: str, service: EndpointServiceProvider, _auth: ServiceAuthProvider
) -> None:
    await service.delete(name)
