"""Server registry routes (spec 10, API-4)."""

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from sqlmodel import func, select

from bundlemcp.api.deps import DbDep, PageDep, RedisDep, ServiceAuthDep
from bundlemcp.api.schemas import Page, ServerRead, ServerUpsert, ToolRead
from bundlemcp.models import BundleServer, McpServer, Tool
from bundlemcp.store.invalidation import InvalidationEvent, publish_invalidation

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/servers", tags=["servers"])


async def _by_name(db, name: str) -> McpServer | None:
    result = await db.execute(select(McpServer).where(McpServer.name == name))
    return result.scalar_one_or_none()


def to_read(server: McpServer) -> ServerRead:
    data = server.model_dump()
    data["static_header_names"] = sorted(server.static_headers)  # SRV-3: names only
    return ServerRead.model_validate(data)


def _apply(server: McpServer, body: ServerUpsert) -> McpServer:
    server.description = body.description
    server.url = body.url
    if body.static_headers:  # write-only merge: empty dict keeps existing secrets
        server.static_headers = body.static_headers
    server.forward_headers = body.forward_headers
    server.auth_mode = body.auth_mode
    server.identity_mode = body.identity_mode
    server.send_identity_header = body.send_identity_header
    return server


async def _probe_async(request: Request, server_id) -> None:
    """SRV-2: validate + discover best-effort; never blocks the API response."""
    discovery = getattr(request.app.state, "discovery", None)
    if discovery is not None:
        await discovery.schedule_probe(server_id)


@router.get("")
async def list_servers(db: DbDep, _auth: ServiceAuthDep, page: PageDep) -> Page[ServerRead]:
    total = (await db.execute(select(func.count()).select_from(McpServer))).scalar_one()
    rows = (
        await db.execute(
            select(McpServer)
            .order_by(McpServer.created_at, McpServer.id)
            .offset(page.offset)
            .limit(page.limit)
        )
    ).scalars()
    return Page(items=[to_read(s) for s in rows], total=total, offset=page.offset, limit=page.limit)


@router.get("/{name}")
async def get_server(name: str, db: DbDep, _auth: ServiceAuthDep) -> ServerRead:
    server = await _by_name(db, name)
    if server is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "server not found")
    return to_read(server)


@router.put("/{name}")
async def upsert_server(
    name: str,
    body: ServerUpsert,
    request: Request,
    db: DbDep,
    redis: RedisDep,
    _auth: ServiceAuthDep,
) -> ServerRead:
    """API-4: config-only upsert by natural key; idempotent; never blocks on probing."""
    if body.name != name:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "body.name must match path name"
        )
    server = await _by_name(db, name)
    created = server is None
    if server is None:
        server = McpServer(name=name, url=body.url)
    _apply(server, body)
    db.add(server)
    await db.commit()
    await db.refresh(server)
    await publish_invalidation(
        redis,
        InvalidationEvent(
            entity_type="server", key=name, action="created" if created else "updated"
        ),
    )
    await _probe_async(request, server.id)
    return to_read(server)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(name: str, db: DbDep, redis: RedisDep, _auth: ServiceAuthDep) -> None:
    """API-6: idempotent delete (404 -> 204 semantics)."""
    server = await _by_name(db, name)
    if server is not None:
        await db.delete(server)  # DOM-2 cascades tools + mappings
        await db.commit()
        await publish_invalidation(
            redis, InvalidationEvent(entity_type="server", key=name, action="deleted")
        )


@router.post("/{name}:rename")
async def rename_server(
    name: str,
    new_name: str,
    db: DbDep,
    redis: RedisDep,
    _auth: ServiceAuthDep,
    force: bool = False,
) -> ServerRead:
    """SRV-5: rejected while in a bundle unless force acknowledges tool-name breakage."""
    server = await _by_name(db, name)
    if server is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "server not found")
    ServerUpsert(name=new_name, url=server.url)  # reuse name validation
    in_bundle = (
        await db.execute(select(BundleServer).where(BundleServer.server_id == server.id).limit(1))
    ).scalar_one_or_none()
    if in_bundle is not None and not force:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "server is a bundle member; renaming changes client-visible tool names — "
            "retry with force=true to acknowledge (SRV-5)",
        )
    server.name = new_name
    await db.commit()
    await db.refresh(server)
    await publish_invalidation(
        redis, InvalidationEvent(entity_type="server", key=new_name, action="updated")
    )
    return to_read(server)


@router.get("/{name}/tools")
async def list_server_tools(
    name: str, db: DbDep, _auth: ServiceAuthDep, page: PageDep
) -> Page[ToolRead]:
    server = await _by_name(db, name)
    if server is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "server not found")
    base = select(Tool).where(Tool.server_id == server.id)
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        await db.execute(base.order_by(Tool.name).offset(page.offset).limit(page.limit))
    ).scalars()
    return Page(
        items=[ToolRead.model_validate(t) for t in rows],
        total=total,
        offset=page.offset,
        limit=page.limit,
    )


@router.post("/{name}:refresh-tools")
async def refresh_tools(name: str, request: Request, db: DbDep, _auth: ServiceAuthDep) -> dict:
    """DISC-1: explicit refresh; runs discovery now and reports the result."""
    server = await _by_name(db, name)
    if server is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "server not found")
    discovery = getattr(request.app.state, "discovery", None)
    if discovery is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "discovery unavailable")
    result = await discovery.discover(server.id)
    return {"discovered": result.discovered, "changed": result.changed, "error": result.error}
