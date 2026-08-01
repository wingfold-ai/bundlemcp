"""Server registry routes, including upstream OAuth client configuration.

Thin controllers: HTTP concerns only; business logic lives in ServerService.
"""

from fastapi import APIRouter, HTTPException, status

from bundlemcp.api.auth import ServiceAuthProvider
from bundlemcp.api.pagination import PageProvider
from bundlemcp.api.providers import ServerServiceProvider
from bundlemcp.schemas import Page, ServerRead, ServerUpsert, ToolRead

router = APIRouter(prefix="/servers", tags=["servers"])


@router.get("")
async def list_servers(
    svc: ServerServiceProvider, _auth: ServiceAuthProvider, page: PageProvider
) -> Page[ServerRead]:
    return await svc.list(offset=page.offset, limit=page.limit)


@router.get("/{name}")
async def get_server(
    name: str, svc: ServerServiceProvider, _auth: ServiceAuthProvider
) -> ServerRead:
    return await svc.get(name)


@router.put("/{name}")
async def upsert_server(
    name: str, body: ServerUpsert, svc: ServerServiceProvider, _auth: ServiceAuthProvider
) -> ServerRead:
    if body.name != name:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "body.name must match path name"
        )
    return await svc.upsert(body)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(name: str, svc: ServerServiceProvider, _auth: ServiceAuthProvider) -> None:
    await svc.delete(name)


@router.post("/{name}:rename")
async def rename_server(
    name: str,
    new_name: str,
    svc: ServerServiceProvider,
    _auth: ServiceAuthProvider,
    force: bool = False,
) -> ServerRead:
    return await svc.rename(name, new_name, force=force)


@router.get("/{name}/tools")
async def list_server_tools(
    name: str, svc: ServerServiceProvider, _auth: ServiceAuthProvider, page: PageProvider
) -> Page[ToolRead]:
    return await svc.list_tools(name, offset=page.offset, limit=page.limit)


@router.post("/{name}:refresh-tools")
async def refresh_tools(name: str, svc: ServerServiceProvider, _auth: ServiceAuthProvider) -> dict:
    return await svc.refresh_tools(name)
