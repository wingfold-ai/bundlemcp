"""FastAPI dependencies: stores and management-API auth (API-2, KEY-2/3/5)."""

from dataclasses import dataclass
from datetime import UTC
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from bundlemcp.models import ApiKey, ApiKeyKind, User, utcnow
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


@dataclass
class Principal:
    """The authenticated management-API caller: an admin user or a service key."""

    kind: str  # "admin" | "service"
    user_id: str | None = None
    api_key_id: str | None = None


_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


async def _admin_session_principal(request: Request, db: AsyncSession) -> Principal | None:
    """ADM: browser cookie session, admin-only. CSRF-guarded (SEC-4).

    Live is_active/is_admin are re-checked against the DB so ADM-6 deactivation
    and demotion take effect immediately, not at session expiry.
    """
    store = getattr(request.app.state, "admin_sessions", None)
    if store is None:
        return None
    from bundlemcp.oauth.adminsessions import SESSION_COOKIE

    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        return None
    session = await store.load(session_id)
    if session is None:
        return None
    import uuid as _uuid

    user = (
        await db.execute(select(User).where(User.id == _uuid.UUID(session.user_id)))
    ).scalar_one_or_none()
    if user is None or not user.is_active or not user.is_admin:
        return None
    if request.method not in _SAFE_METHODS:
        # SEC-4: cookie-authenticated mutations require a same-origin Origin/Referer
        origin = request.headers.get("origin") or request.headers.get("referer")
        expected = str(request.app.state.settings.public_url).rstrip("/")
        if origin is None or not origin.startswith(expected):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF origin check failed (SEC-4)")
    return Principal(kind="admin", user_id=session.user_id)


async def require_management_auth(request: Request, db: DbDep) -> Principal:
    """API-2: admin session cookie OR service API key."""
    admin = await _admin_session_principal(request, db)
    if admin is not None:
        return admin
    key = await resolve_api_key(request, db)
    if key is not None and key.kind == ApiKeyKind.SERVICE:
        return Principal(kind="service", api_key_id=str(key.id))
    if key is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="key is not service-kind (KEY-2)"
        )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="admin session or service API key required"
    )


ServiceAuthDep = Annotated[Principal, Depends(require_management_auth)]


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
