"""Bundle composition + tool curation routes.

Thin controllers: HTTP concerns only; business logic lives in BundleService.
"""

import uuid

from fastapi import APIRouter, HTTPException, status

from bundlemcp.api.auth import ServiceAuthProvider
from bundlemcp.api.pagination import PageProvider
from bundlemcp.api.providers import BundleServiceProvider
from bundlemcp.schemas import (
    BundleRead,
    BundleServerUpdate,
    BundleToolUpdate,
    BundleUpsert,
    Page,
)

router = APIRouter(prefix="/bundles", tags=["bundles"])


@router.get("")
async def list_bundles(
    svc: BundleServiceProvider, _auth: ServiceAuthProvider, page: PageProvider
) -> Page[BundleRead]:
    return await svc.list(offset=page.offset, limit=page.limit)


@router.put("/{name}")
async def upsert_bundle(
    name: str, body: BundleUpsert, svc: BundleServiceProvider, _auth: ServiceAuthProvider
) -> BundleRead:
    if body.name != name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "body.name must match path name")
    return await svc.upsert(body)


@router.get("/{name}")
async def get_bundle(
    name: str, svc: BundleServiceProvider, _auth: ServiceAuthProvider
) -> BundleRead:
    return await svc.get(name)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bundle(name: str, svc: BundleServiceProvider, _auth: ServiceAuthProvider) -> None:
    await svc.delete(name)


@router.put("/{name}/servers/{server_name}")
async def add_or_update_member(
    name: str,
    server_name: str,
    body: BundleServerUpdate,
    svc: BundleServiceProvider,
    _auth: ServiceAuthProvider,
) -> dict:
    return await svc.set_member(name, server_name, body)


@router.delete("/{name}/servers/{server_name}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    name: str, server_name: str, svc: BundleServiceProvider, _auth: ServiceAuthProvider
) -> None:
    await svc.remove_member(name, server_name)


@router.put("/{name}/tools/{tool_id}")
async def curate_tool(
    name: str,
    tool_id: uuid.UUID,
    body: BundleToolUpdate,
    svc: BundleServiceProvider,
    _auth: ServiceAuthProvider,
) -> dict:
    return await svc.curate_tool(name, tool_id, body)
