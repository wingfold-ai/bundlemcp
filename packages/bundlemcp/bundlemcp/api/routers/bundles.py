"""Bundle composition + tool curation routes (specs 12/13)."""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlmodel import func, select

from bundlemcp.api.deps import DbDep, PageDep, RedisDep, ServiceAuthDep
from bundlemcp.api.schemas import (
    BundleRead,
    BundleServerUpdate,
    BundleToolUpdate,
    BundleUpsert,
    Page,
)
from bundlemcp.models import Bundle, BundleServer, BundleTool, McpServer, Tool
from bundlemcp.store.invalidation import InvalidationEvent, publish_invalidation

router = APIRouter(prefix="/bundles", tags=["bundles"])


async def _get_bundle(db, name: str) -> Bundle:
    bundle = (await db.execute(select(Bundle).where(Bundle.name == name))).scalar_one_or_none()
    if bundle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "bundle not found")
    return bundle


async def _invalidate(redis, name: str, action: str = "updated") -> None:
    await publish_invalidation(
        redis, InvalidationEvent(entity_type="bundle", key=name, action=action)
    )


@router.get("")
async def list_bundles(db: DbDep, _auth: ServiceAuthDep, page: PageDep) -> Page[BundleRead]:
    total = (await db.execute(select(func.count()).select_from(Bundle))).scalar_one()
    rows = (
        await db.execute(
            select(Bundle)
            .order_by(Bundle.created_at, Bundle.id)
            .offset(page.offset)
            .limit(page.limit)
        )
    ).scalars()
    return Page(
        items=[BundleRead.model_validate(b) for b in rows],
        total=total,
        offset=page.offset,
        limit=page.limit,
    )


@router.put("/{name}")
async def upsert_bundle(
    name: str, body: BundleUpsert, db: DbDep, redis: RedisDep, _auth: ServiceAuthDep
) -> BundleRead:
    if body.name != name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "body.name must match path name")
    bundle = (await db.execute(select(Bundle).where(Bundle.name == name))).scalar_one_or_none()
    created = bundle is None
    if bundle is None:
        bundle = Bundle(name=name)
    bundle.description = body.description
    db.add(bundle)
    await db.commit()
    await db.refresh(bundle)
    await _invalidate(redis, name, "created" if created else "updated")
    return BundleRead.model_validate(bundle)


@router.get("/{name}")
async def get_bundle(name: str, db: DbDep, _auth: ServiceAuthDep) -> BundleRead:
    return BundleRead.model_validate(await _get_bundle(db, name))


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bundle(name: str, db: DbDep, redis: RedisDep, _auth: ServiceAuthDep) -> None:
    bundle = (await db.execute(select(Bundle).where(Bundle.name == name))).scalar_one_or_none()
    if bundle is not None:
        await db.delete(bundle)  # DOM-2 cascades mappings + endpoints
        await db.commit()
        await _invalidate(redis, name, "deleted")


@router.put("/{name}/servers/{server_name}")
async def add_or_update_member(
    name: str,
    server_name: str,
    body: BundleServerUpdate,
    db: DbDep,
    redis: RedisDep,
    _auth: ServiceAuthDep,
) -> dict:
    """BND-4/BND-6: add a member server or toggle it; upsert semantics (API-6)."""
    bundle = await _get_bundle(db, name)
    server = (
        await db.execute(select(McpServer).where(McpServer.name == server_name))
    ).scalar_one_or_none()
    if server is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "server not found")
    mapping = (
        await db.execute(
            select(BundleServer).where(
                BundleServer.bundle_id == bundle.id, BundleServer.server_id == server.id
            )
        )
    ).scalar_one_or_none()
    if mapping is None:
        mapping = BundleServer(bundle_id=bundle.id, server_id=server.id)
    mapping.enabled = body.enabled
    db.add(mapping)
    await db.commit()
    await _invalidate(redis, name)
    return {"bundle": name, "server": server_name, "enabled": mapping.enabled}


@router.delete("/{name}/servers/{server_name}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    name: str, server_name: str, db: DbDep, redis: RedisDep, _auth: ServiceAuthDep
) -> None:
    bundle = await _get_bundle(db, name)
    server = (
        await db.execute(select(McpServer).where(McpServer.name == server_name))
    ).scalar_one_or_none()
    if server is None:
        return
    mapping = (
        await db.execute(
            select(BundleServer).where(
                BundleServer.bundle_id == bundle.id, BundleServer.server_id == server.id
            )
        )
    ).scalar_one_or_none()
    if mapping is not None:
        await db.delete(mapping)
        await db.commit()
        await _invalidate(redis, name)


@router.put("/{name}/tools/{tool_id}")
async def curate_tool(
    name: str,
    tool_id: uuid.UUID,
    body: BundleToolUpdate,
    db: DbDep,
    redis: RedisDep,
    _auth: ServiceAuthDep,
) -> dict:
    """TM-1..TM-4, TM-6: per-bundle enable/disable + overrides."""
    bundle = await _get_bundle(db, name)
    tool = (await db.execute(select(Tool).where(Tool.id == tool_id))).scalar_one_or_none()
    if tool is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tool not found")

    if body.override_name is not None:
        # TM-3: override names unique within the bundle vs other overrides
        clash = (
            await db.execute(
                select(BundleTool).where(
                    BundleTool.bundle_id == bundle.id,
                    BundleTool.override_name == body.override_name,
                    BundleTool.tool_id != tool_id,
                )
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "override_name already used in this bundle (TM-3)"
            )

    mapping = (
        await db.execute(
            select(BundleTool).where(
                BundleTool.bundle_id == bundle.id, BundleTool.tool_id == tool_id
            )
        )
    ).scalar_one_or_none()
    if mapping is None:
        mapping = BundleTool(bundle_id=bundle.id, tool_id=tool_id)
    mapping.enabled = body.enabled
    mapping.override_name = body.override_name
    mapping.override_title = body.override_title
    mapping.override_description = body.override_description
    mapping.override_annotations = body.override_annotations
    db.add(mapping)
    await db.commit()
    await publish_invalidation(
        redis, InvalidationEvent(entity_type="bundle_tool", key=str(tool_id), action="updated")
    )
    await _invalidate(redis, name)
    return {"bundle": name, "tool_id": str(tool_id), "enabled": mapping.enabled}
