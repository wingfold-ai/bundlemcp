"""Bundle composition + tool curation routes.

Thin controllers: HTTP concerns only; business logic lives in BundleService.
"""

import uuid

from fastapi import APIRouter, HTTPException, status

from bundlemcp.api.auth import ServiceAuthProvider
from bundlemcp.api.pagination import PageProvider
from bundlemcp.providers import BundleServiceProvider
from bundlemcp.schemas import (
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

router = APIRouter(prefix="/bundles", tags=["bundles"])


@router.get("")
async def list_bundles(
    service: BundleServiceProvider, _auth: ServiceAuthProvider, page: PageProvider
) -> Page[BundleRead]:
    return await service.list(offset=page.offset, limit=page.limit)


@router.put("/{name}")
async def upsert_bundle(
    name: str, body: BundleUpsert, service: BundleServiceProvider, _auth: ServiceAuthProvider
) -> BundleRead:
    if body.name != name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "body.name must match path name")
    return await service.upsert(body)


@router.get("/{name}")
async def get_bundle(
    name: str, service: BundleServiceProvider, _auth: ServiceAuthProvider
) -> BundleRead:
    return await service.get(name)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bundle(
    name: str, service: BundleServiceProvider, _auth: ServiceAuthProvider
) -> None:
    await service.delete(name)


@router.get("/{name}/servers")
async def list_members(
    name: str, service: BundleServiceProvider, _auth: ServiceAuthProvider
) -> list[BundleMemberRead]:
    return await service.list_members(name)


@router.get("/{name}/tools")
async def list_bundle_tools(
    name: str, service: BundleServiceProvider, _auth: ServiceAuthProvider
) -> list[BundleToolRead]:
    return await service.list_tools(name)


@router.put("/{name}/servers/{server_name}")
async def add_or_update_member(
    name: str,
    server_name: str,
    body: BundleServerUpdate,
    service: BundleServiceProvider,
    _auth: ServiceAuthProvider,
) -> BundleMembershipRead:
    return await service.set_member(name, server_name, body)


@router.delete("/{name}/servers/{server_name}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    name: str, server_name: str, service: BundleServiceProvider, _auth: ServiceAuthProvider
) -> None:
    await service.remove_member(name, server_name)


@router.put("/{name}/tools/{tool_id}")
async def curate_tool(
    name: str,
    tool_id: uuid.UUID,
    body: BundleToolUpdate,
    service: BundleServiceProvider,
    _auth: ServiceAuthProvider,
) -> ToolCurationRead:
    return await service.curate_tool(name, tool_id, body)
