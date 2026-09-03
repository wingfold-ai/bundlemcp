"""Server registry routes, including upstream OAuth client configuration.

Thin controllers: HTTP concerns only; business logic lives in ServerService.
"""

from fastapi import APIRouter, HTTPException, status

from bundlemcp.api.auth import ServiceAuthProvider
from bundlemcp.api.pagination import PageProvider
from bundlemcp.providers import ServerServiceProvider
from bundlemcp.schemas import Page, ServerRead, ServerUpsert, ToolRead, UpstreamOAuthConfig

router = APIRouter(prefix="/servers", tags=["servers"])


@router.get("")
async def list_servers(
    service: ServerServiceProvider, _auth: ServiceAuthProvider, page: PageProvider
) -> Page[ServerRead]:
    return await service.list(offset=page.offset, limit=page.limit)


@router.get("/{name}")
async def get_server(
    name: str, service: ServerServiceProvider, _auth: ServiceAuthProvider
) -> ServerRead:
    return await service.get(name)


@router.put("/{name}")
async def upsert_server(
    name: str, body: ServerUpsert, service: ServerServiceProvider, _auth: ServiceAuthProvider
) -> ServerRead:
    if body.name != name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "body.name must match path name")
    return await service.upsert(body)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(
    name: str, service: ServerServiceProvider, _auth: ServiceAuthProvider
) -> None:
    await service.delete(name)


@router.post("/{name}:rename")
async def rename_server(
    name: str,
    new_name: str,
    service: ServerServiceProvider,
    _auth: ServiceAuthProvider,
    force: bool = False,
) -> ServerRead:
    return await service.rename(name, new_name, force=force)


@router.get("/{name}/tools")
async def list_server_tools(
    name: str, service: ServerServiceProvider, _auth: ServiceAuthProvider, page: PageProvider
) -> Page[ToolRead]:
    return await service.list_tools(name, offset=page.offset, limit=page.limit)


@router.post("/{name}:refresh-tools")
async def refresh_tools(
    name: str, service: ServerServiceProvider, _auth: ServiceAuthProvider
) -> dict:
    return await service.refresh_tools(name)


# --- upstream OAuth client config + status (spec 23, UPO-1/5) ---


@router.put("/{name}/upstream-oauth")
async def set_upstream_oauth(
    name: str, body: UpstreamOAuthConfig, service: ServerServiceProvider, _auth: ServiceAuthProvider
) -> dict:
    return await service.set_upstream_oauth(name, body)


@router.get("/{name}/upstream-oauth")
async def upstream_oauth_status(
    name: str, service: ServerServiceProvider, _auth: ServiceAuthProvider
) -> dict:
    return await service.upstream_oauth_status(name)


@router.delete("/{name}/upstream-oauth/token", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_upstream_oauth(
    name: str, service: ServerServiceProvider, _auth: ServiceAuthProvider
) -> None:
    await service.disconnect_upstream_oauth(name)
