"""Endpoint routes (specs 14/15)."""

from fastapi import APIRouter, HTTPException, status
from sqlmodel import func, select

from bundlemcp.api.deps import DbDep, PageDep, RedisDep, ServiceAuthDep
from bundlemcp.api.schemas import EndpointRead, EndpointUpsert, Page
from bundlemcp.api.validators import endpoint_violates_per_user_upstream
from bundlemcp.models import Bundle, Endpoint, EndpointProfile
from bundlemcp.store.invalidation import InvalidationEvent, publish_invalidation

router = APIRouter(prefix="/endpoints", tags=["endpoints"])


@router.get("")
async def list_endpoints(db: DbDep, _auth: ServiceAuthDep, page: PageDep) -> Page[EndpointRead]:
    total = (await db.execute(select(func.count()).select_from(Endpoint))).scalar_one()
    rows = (
        await db.execute(
            select(Endpoint)
            .order_by(Endpoint.created_at, Endpoint.id)
            .offset(page.offset)
            .limit(page.limit)
        )
    ).scalars()
    return Page(
        items=[EndpointRead.model_validate(e) for e in rows],
        total=total,
        offset=page.offset,
        limit=page.limit,
    )


@router.get("/profiles", tags=["profiles"])
async def list_profiles(_auth: ServiceAuthDep) -> list[dict]:
    """PROF-5: profiles are code presets, listed so the UI stays data-driven."""
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
async def get_endpoint(name: str, db: DbDep, _auth: ServiceAuthDep) -> EndpointRead:
    ep = (await db.execute(select(Endpoint).where(Endpoint.name == name))).scalar_one_or_none()
    if ep is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "endpoint not found")
    return EndpointRead.model_validate(ep)


@router.put("/{name}")
async def upsert_endpoint(
    name: str, body: EndpointUpsert, db: DbDep, redis: RedisDep, _auth: ServiceAuthDep
) -> EndpointRead:
    if body.name != name:
        # EP-8: changing the public URL needs an explicit rename with force
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "body.name must match path name; rename via :rename with force (EP-8)",
        )
    bundle = (
        await db.execute(select(Bundle).where(Bundle.name == body.bundle_name))
    ).scalar_one_or_none()
    if bundle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "bundle not found")
    # UPO-6: a none-only endpoint can't expose a bundle with a per_user upstream
    if await endpoint_violates_per_user_upstream(
        db, bundle.id, [m.value for m in body.auth_modes]
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "a 'none'-auth endpoint cannot expose a bundle with a per_user upstream server (UPO-6)",
        )
    ep = (await db.execute(select(Endpoint).where(Endpoint.name == name))).scalar_one_or_none()
    created = ep is None
    if ep is None:
        ep = Endpoint(name=name, bundle_id=bundle.id)
    ep.bundle_id = bundle.id
    ep.profile = body.profile
    ep.auth_modes = [m.value for m in body.auth_modes]
    ep.rate_limit = body.rate_limit
    ep.enabled = body.enabled
    db.add(ep)
    await db.commit()
    await db.refresh(ep)
    await publish_invalidation(
        redis,
        InvalidationEvent(
            entity_type="endpoint", key=name, action="created" if created else "updated"
        ),
    )
    return EndpointRead.model_validate(ep)


@router.post("/{name}:rename")
async def rename_endpoint(
    name: str,
    new_name: str,
    db: DbDep,
    redis: RedisDep,
    _auth: ServiceAuthDep,
    force: bool = False,
) -> EndpointRead:
    """EP-8: rename breaks every connected client's URL; force required."""
    if not force:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "renaming an endpoint changes its public URL and breaks connected clients — "
            "retry with force=true (EP-8)",
        )
    ep = (await db.execute(select(Endpoint).where(Endpoint.name == name))).scalar_one_or_none()
    if ep is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "endpoint not found")
    # reuse DTO name validation (reserved names, slug)
    EndpointUpsert(name=new_name, bundle_name="x", allow_unauthenticated=True)
    ep.name = new_name
    await db.commit()
    await db.refresh(ep)
    await publish_invalidation(
        redis, InvalidationEvent(entity_type="endpoint", key=new_name, action="updated")
    )
    return EndpointRead.model_validate(ep)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_endpoint(name: str, db: DbDep, redis: RedisDep, _auth: ServiceAuthDep) -> None:
    ep = (await db.execute(select(Endpoint).where(Endpoint.name == name))).scalar_one_or_none()
    if ep is not None:
        await db.delete(ep)
        await db.commit()
        await publish_invalidation(
            redis, InvalidationEvent(entity_type="endpoint", key=name, action="deleted")
        )
