"""API key business logic."""

import uuid

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from bundlemcp.crypto import API_KEY_PREFIX, display_prefix, generate_token, hash_token
from bundlemcp.models import ApiKey
from bundlemcp.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyRead, Page
from bundlemcp.services.errors import NotFoundError
from bundlemcp.store.invalidation import InvalidationEvent, publish_invalidation


class ApiKeyService:
    def __init__(self, db: AsyncSession, redis: Redis) -> None:
        self._db = db
        self._redis = redis

    async def _by_id(self, key_id: uuid.UUID) -> ApiKey | None:
        return (
            await self._db.execute(select(ApiKey).where(ApiKey.id == key_id))
        ).scalar_one_or_none()

    async def list(self, *, offset: int, limit: int) -> Page[ApiKeyRead]:
        total = (await self._db.execute(select(func.count()).select_from(ApiKey))).scalar_one()
        rows = (
            await self._db.execute(
                select(ApiKey).order_by(ApiKey.created_at, ApiKey.id).offset(offset).limit(limit)
            )
        ).scalars()
        return Page(
            items=[ApiKeyRead.model_validate(k) for k in rows],
            total=total,
            offset=offset,
            limit=limit,
        )

    async def create(self, body: ApiKeyCreate) -> ApiKeyCreated:
        """The key value is returned exactly once; only the hash is stored."""
        value = generate_token(API_KEY_PREFIX)
        key = ApiKey(
            name=body.name,
            key_hash=hash_token(value),
            key_prefix=display_prefix(value),
            kind=body.kind,
            endpoint_ids=[str(e) for e in body.endpoint_ids],
        )
        self._db.add(key)
        await self._db.commit()
        await self._db.refresh(key)
        return ApiKeyCreated(**ApiKeyRead.model_validate(key).model_dump(), key=value)

    async def deactivate(self, key_id: uuid.UUID) -> ApiKeyRead:
        """Takes effect via a published invalidation event, not cache TTL."""
        key = await self._by_id(key_id)
        if key is None:
            raise NotFoundError("key not found")
        key.is_active = False
        await self._db.commit()
        await self._db.refresh(key)
        await publish_invalidation(
            self._redis,
            InvalidationEvent(entity_type="api_key", key=str(key_id), action="updated"),
        )
        return ApiKeyRead.model_validate(key)

    async def delete(self, key_id: uuid.UUID) -> None:
        key = await self._by_id(key_id)
        if key is not None:
            await self._db.delete(key)
            await self._db.commit()
            await publish_invalidation(
                self._redis,
                InvalidationEvent(entity_type="api_key", key=str(key_id), action="deleted"),
            )
