"""FastAPI dependencies: stores and management-API auth (API-2, KEY-2/3/5)."""

from datetime import UTC
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from bundlemcp.models import ApiKey, ApiKeyKind, utcnow
from bundlemcp.security import API_KEY_PREFIX, hash_token


async def get_db(request: Request) -> AsyncSession:
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


async def get_redis(request: Request) -> Redis:
    return request.app.state.redis


DbDep = Annotated[AsyncSession, Depends(get_db)]
RedisDep = Annotated[Redis, Depends(get_redis)]


def _extract_key(request: Request) -> str | None:
    """KEY-3: Authorization: Bearer bmcp_sk_… or X-API-Key. Never query params."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer ") and auth[7:].startswith(API_KEY_PREFIX):
        return auth[7:]
    header = request.headers.get("x-api-key")
    if header and header.startswith(API_KEY_PREFIX):
        return header
    return None


async def resolve_api_key(request: Request, db: AsyncSession) -> ApiKey | None:
    raw = _extract_key(request)
    if raw is None:
        return None
    result = await db.execute(select(ApiKey).where(ApiKey.key_hash == hash_token(raw)))
    key = result.scalar_one_or_none()
    if key is None or not key.is_active:
        return None
    # KEY-4: coarse last_used_at maintenance (sqlite returns naive datetimes — assume UTC)
    last = key.last_used_at
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    if last is None or (utcnow() - last).total_seconds() > 60:
        key.last_used_at = utcnow()
        await db.commit()
    return key


async def require_service_auth(request: Request, db: DbDep) -> ApiKey:
    """API-2: service API key (admin OIDC sessions to be added with the UI phase)."""
    key = await resolve_api_key(request, db)
    if key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="service API key required"
        )
    if key.kind != ApiKeyKind.SERVICE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="key is not service-kind (KEY-2)"
        )
    return key


ServiceAuthDep = Annotated[ApiKey, Depends(require_service_auth)]


class Pagination:
    """API-5: default 50, max 500, stable ordering handled per-router."""

    def __init__(
        self,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
    ) -> None:
        self.offset = offset
        self.limit = limit


PageDep = Annotated[Pagination, Depends(Pagination)]
