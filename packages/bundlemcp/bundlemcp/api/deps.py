"""FastAPI dependencies: stores, service wiring, and the management-API auth edge.

Business logic lives in ``bundlemcp.services``; this module is the thin FastAPI
seam that builds services from app state, parses the request, applies transport
concerns (CSRF), and maps the accept-either auth policy to 401/403.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.models import ApiKeyKind
from bundlemcp.services import (
    ApiKeyService,
    AuthService,
    BundleService,
    ConfigService,
    EndpointService,
    Principal,
    ServerService,
    UserService,
)


async def get_db(request: Request) -> AsyncSession:
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


async def get_redis(request: Request) -> Redis:
    return request.app.state.redis


DbDep = Annotated[AsyncSession, Depends(get_db)]
RedisDep = Annotated[Redis, Depends(get_redis)]


def get_auth_service(request: Request, db: DbDep) -> AuthService:
    return AuthService(db, admin_sessions=getattr(request.app.state, "admin_sessions", None))


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


async def require_management_auth(request: Request, auth: AuthServiceDep) -> Principal:
    """Accept either an admin session cookie or a service-kind API key."""
    from bundlemcp.oauth.adminsessions import SESSION_COOKIE

    admin = await auth.admin_principal(request.cookies.get(SESSION_COOKIE))
    if admin is not None:
        if request.method not in _SAFE_METHODS:
            # SEC-4: cookie-authenticated mutations require a same-origin Origin/Referer
            origin = request.headers.get("origin") or request.headers.get("referer")
            expected = str(request.app.state.settings.public_url).rstrip("/")
            if origin is None or not origin.startswith(expected):
                raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF origin check failed (SEC-4)")
        return admin
    key = await auth.authenticate_api_key(
        authorization=request.headers.get("authorization"),
        x_api_key=request.headers.get("x-api-key"),
    )
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
    """Offset/limit pagination: default 50, max 500, stable ordering handled per-router."""

    def __init__(
        self,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
    ) -> None:
        self.offset = offset
        self.limit = limit


PageDep = Annotated[Pagination, Depends(Pagination)]


# --- service providers: construct framework-free services from app state ---


def get_server_service(request: Request, db: DbDep, redis: RedisDep) -> ServerService:
    return ServerService(
        db,
        redis,
        discovery=getattr(request.app.state, "discovery", None),
        settings=request.app.state.settings,
        upstream_tokens=getattr(request.app.state, "upstream_tokens", None),
    )


def get_bundle_service(db: DbDep, redis: RedisDep) -> BundleService:
    return BundleService(db, redis)


def get_endpoint_service(db: DbDep, redis: RedisDep) -> EndpointService:
    return EndpointService(db, redis)


def get_api_key_service(db: DbDep, redis: RedisDep) -> ApiKeyService:
    return ApiKeyService(db, redis)


def get_user_service(db: DbDep) -> UserService:
    return UserService(db)


def get_config_service(db: DbDep, redis: RedisDep) -> ConfigService:
    return ConfigService(db, redis)


ServerServiceDep = Annotated[ServerService, Depends(get_server_service)]
BundleServiceDep = Annotated[BundleService, Depends(get_bundle_service)]
EndpointServiceDep = Annotated[EndpointService, Depends(get_endpoint_service)]
ApiKeyServiceDep = Annotated[ApiKeyService, Depends(get_api_key_service)]
UserServiceDep = Annotated[UserService, Depends(get_user_service)]
ConfigServiceDep = Annotated[ConfigService, Depends(get_config_service)]
