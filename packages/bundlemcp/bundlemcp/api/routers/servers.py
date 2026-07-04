"""Server registry routes, including upstream OAuth client configuration.

Thin controllers: HTTP concerns only; business logic lives in ServerService.
"""

from fastapi import APIRouter, HTTPException, status

from bundlemcp.api.deps import PageDep, ServerServiceDep, ServiceAuthDep
from bundlemcp.schemas import Page, ServerRead, ServerUpsert, ToolRead, UpstreamOAuthConfig

router = APIRouter(prefix="/servers", tags=["servers"])


@router.get("")
async def list_servers(
    svc: ServerServiceDep, _auth: ServiceAuthDep, page: PageDep
) -> Page[ServerRead]:
    return await svc.list(offset=page.offset, limit=page.limit)


@router.get("/{name}")
async def get_server(name: str, svc: ServerServiceDep, _auth: ServiceAuthDep) -> ServerRead:
    return await svc.get(name)


@router.put("/{name}")
async def upsert_server(
    name: str, body: ServerUpsert, svc: ServerServiceDep, _auth: ServiceAuthDep
) -> ServerRead:
    if body.name != name:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "body.name must match path name"
        )
    return await svc.upsert(body)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(name: str, svc: ServerServiceDep, _auth: ServiceAuthDep) -> None:
    await svc.delete(name)


@router.post("/{name}:rename")
async def rename_server(
    name: str,
    new_name: str,
    svc: ServerServiceDep,
    _auth: ServiceAuthDep,
    force: bool = False,
) -> ServerRead:
    return await svc.rename(name, new_name, force=force)


@router.get("/{name}/tools")
async def list_server_tools(
    name: str, svc: ServerServiceDep, _auth: ServiceAuthDep, page: PageDep
) -> Page[ToolRead]:
    return await svc.list_tools(name, offset=page.offset, limit=page.limit)


@router.post("/{name}:refresh-tools")
async def refresh_tools(name: str, svc: ServerServiceDep, _auth: ServiceAuthDep) -> dict:
    return await svc.refresh_tools(name)


# --- upstream OAuth client config + status (spec 23, UPO-1/5) ---


@router.put("/{name}/upstream-oauth")
async def set_upstream_oauth(
    name: str, body: UpstreamOAuthConfig, svc: ServerServiceDep, _auth: ServiceAuthDep
) -> dict:
    return await svc.set_upstream_oauth(name, body)


@router.get("/{name}/upstream-oauth")
async def upstream_oauth_status(name: str, svc: ServerServiceDep, _auth: ServiceAuthDep) -> dict:
    return await svc.upstream_oauth_status(name)


@router.delete("/{name}/upstream-oauth/token", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_upstream_oauth(
    name: str, svc: ServerServiceDep, _auth: ServiceAuthDep
) -> None:
    await svc.disconnect_upstream_oauth(name)
