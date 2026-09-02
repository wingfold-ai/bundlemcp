"""FastAPI providers: glue that builds stores and services from app state.

These are app-owned dependency *providers* (not third-party dependencies): each
``get_*`` yields a value and the ``*Provider`` alias injects it into a route.
Auth lives in ``api/auth.py``, pagination in ``api/pagination.py``.
"""

from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bundlemcp.gateway.ratelimit import AuthFailureLimiter
from bundlemcp.services import (
    ApiKeyService,
    AuditService,
    BundleService,
    ConfigService,
    EndpointService,
    ServerService,
    UserService,
)
from bundlemcp.settings import Settings


async def get_db(request: Request) -> AsyncSession:
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    """The factory itself, for handlers that need several short transactions.

    Prefer ``DbProvider`` for a single request-scoped session; take the factory
    only when the handler deliberately opens and commits more than one.
    """
    return request.app.state.session_factory


async def get_redis(request: Request) -> Redis:
    return request.app.state.redis


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_auth_failure_limiter(request: Request) -> AuthFailureLimiter:
    return request.app.state.auth_failure_limiter


DbProvider = Annotated[AsyncSession, Depends(get_db)]
SessionFactoryProvider = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
RedisProvider = Annotated[Redis, Depends(get_redis)]
SettingsProvider = Annotated[Settings, Depends(get_app_settings)]
AuthFailureLimiterProvider = Annotated[AuthFailureLimiter, Depends(get_auth_failure_limiter)]


def get_server_service(request: Request, db: DbProvider, redis: RedisProvider) -> ServerService:
    return ServerService(
        db,
        redis,
        discovery=getattr(request.app.state, "discovery", None),
        settings=request.app.state.settings,
        upstream_tokens=getattr(request.app.state, "upstream_tokens", None),
    )


def get_bundle_service(db: DbProvider, redis: RedisProvider) -> BundleService:
    return BundleService(db, redis)


def get_endpoint_service(db: DbProvider, redis: RedisProvider) -> EndpointService:
    return EndpointService(db, redis)


def get_api_key_service(db: DbProvider, redis: RedisProvider) -> ApiKeyService:
    return ApiKeyService(db, redis)


def get_user_service(db: DbProvider) -> UserService:
    return UserService(db)


def get_config_service(db: DbProvider, redis: RedisProvider) -> ConfigService:
    return ConfigService(db, redis)


def get_audit_service(db: DbProvider) -> AuditService:
    return AuditService(db)


ServerServiceProvider = Annotated[ServerService, Depends(get_server_service)]
BundleServiceProvider = Annotated[BundleService, Depends(get_bundle_service)]
EndpointServiceProvider = Annotated[EndpointService, Depends(get_endpoint_service)]
ApiKeyServiceProvider = Annotated[ApiKeyService, Depends(get_api_key_service)]
UserServiceProvider = Annotated[UserService, Depends(get_user_service)]
ConfigServiceProvider = Annotated[ConfigService, Depends(get_config_service)]
AuditServiceProvider = Annotated[AuditService, Depends(get_audit_service)]
