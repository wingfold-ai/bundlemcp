"""Endpoint routes.

Thin controllers: HTTP concerns only; business logic lives in EndpointService.
"""

from fastapi import APIRouter, HTTPException, status

from bundlemcp.api.auth import ServiceAuthProvider
from bundlemcp.api.pagination import PageProvider
from bundlemcp.api.providers import EndpointServiceProvider
from bundlemcp.models import EndpointProfile
from bundlemcp.schemas import EndpointRead, EndpointUpsert, Page

router = APIRouter(prefix="/endpoints", tags=["endpoints"])


@router.get("")
async def list_endpoints(
    svc: EndpointServiceProvider, _auth: ServiceAuthProvider, page: PageProvider
) -> Page[EndpointRead]:
    return await svc.list(offset=page.offset, limit=page.limit)


@router.get("/profiles", tags=["profiles"])
async def list_profiles(_auth: ServiceAuthProvider) -> list[dict]:
    """Profiles are code presets, listed here so the UI stays data-driven."""
    return [
        {"name": EndpointProfile.DEFAULT, "description": "Passthrough; any auth mode"},
        {
            "name": EndpointProfile.CLAUDE,
            "description": "claude.ai remote connector: OAuth-only, passthrough tools",
        },
        {
            "name": EndpointProfile.CHATGPT,
            "description": (
                "Re-annotates write tools as read-safe (PROF-3) — tools still perform "
                "their real operations upstream"
            ),
            "warning": "annotations no longer reflect true tool behavior",
        },
    ]


@router.get("/{name}")
async def get_endpoint(
    name: str, svc: EndpointServiceProvider, _auth: ServiceAuthProvider
) -> EndpointRead:
    return await svc.get(name)


@router.put("/{name}")
async def upsert_endpoint(
    name: str, body: EndpointUpsert, svc: EndpointServiceProvider, _auth: ServiceAuthProvider
) -> EndpointRead:
    if body.name != name:
        # EP-8: changing the public URL needs an explicit rename with force
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "body.name must match path name; rename via :rename with force (EP-8)",
        )
    return await svc.upsert(body)


@router.post("/{name}:rename")
async def rename_endpoint(
    name: str,
    new_name: str,
    svc: EndpointServiceProvider,
    _auth: ServiceAuthProvider,
    force: bool = False,
) -> EndpointRead:
    return await svc.rename(name, new_name, force=force)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_endpoint(
    name: str, svc: EndpointServiceProvider, _auth: ServiceAuthProvider
) -> None:
    await svc.delete(name)
