"""API key routes (spec 22)."""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlmodel import func, select

from bundlemcp.api.deps import DbDep, PageDep, RedisDep, ServiceAuthDep
from bundlemcp.api.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyRead, Page
from bundlemcp.models import ApiKey
from bundlemcp.security import API_KEY_PREFIX, display_prefix, generate_token, hash_token
from bundlemcp.store.invalidation import InvalidationEvent, publish_invalidation

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.get("")
async def list_keys(db: DbDep, _auth: ServiceAuthDep, page: PageDep) -> Page[ApiKeyRead]:
    total = (await db.execute(select(func.count()).select_from(ApiKey))).scalar_one()
    rows = (
        await db.execute(
            select(ApiKey)
            .order_by(ApiKey.created_at, ApiKey.id)
            .offset(page.offset)
            .limit(page.limit)
        )
    ).scalars()
    return Page(
        items=[ApiKeyRead.model_validate(k) for k in rows],
        total=total,
        offset=page.offset,
        limit=page.limit,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_key(body: ApiKeyCreate, db: DbDep, _auth: ServiceAuthDep) -> ApiKeyCreated:
    """KEY-1: the key value is returned exactly once, only the hash is stored."""
    value = generate_token(API_KEY_PREFIX)
    key = ApiKey(
        name=body.name,
        key_hash=hash_token(value),
        key_prefix=display_prefix(value),
        kind=body.kind,
        endpoint_ids=[str(e) for e in body.endpoint_ids],
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)
    return ApiKeyCreated(**ApiKeyRead.model_validate(key).model_dump(), key=value)


@router.post("/{key_id}:deactivate")
async def deactivate_key(
    key_id: uuid.UUID, db: DbDep, redis: RedisDep, _auth: ServiceAuthDep
) -> ApiKeyRead:
    """KEY-4: takes effect via STP invalidation, not cache TTL."""
    key = (await db.execute(select(ApiKey).where(ApiKey.id == key_id))).scalar_one_or_none()
    if key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "key not found")
    key.is_active = False
    await db.commit()
    await db.refresh(key)
    await publish_invalidation(
        redis, InvalidationEvent(entity_type="api_key", key=str(key_id), action="updated")
    )
    return ApiKeyRead.model_validate(key)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_key(key_id: uuid.UUID, db: DbDep, redis: RedisDep, _auth: ServiceAuthDep) -> None:
    key = (await db.execute(select(ApiKey).where(ApiKey.id == key_id))).scalar_one_or_none()
    if key is not None:
        await db.delete(key)
        await db.commit()
        await publish_invalidation(
            redis, InvalidationEvent(entity_type="api_key", key=str(key_id), action="deleted")
        )
