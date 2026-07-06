"""FastAPI providers: glue that builds stores and services from app state.

These are app-owned dependency *providers* (not third-party dependencies): each
``get_*`` yields a value and the ``*Provider`` alias injects it into a route.
Auth lives in ``api/auth.py``, pagination in ``api/pagination.py``.
"""

from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.services import (
    ApiKeyService,
    AuditService,
    BundleService,
    ConfigService,
    EndpointService,
    ServerService,
    UserService,
)


async def get_db(request: Request) -> AsyncSession:
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


async def get_redis(request: Request) -> Redis:
    return request.app.state.redis


DbProvider = Annotated[AsyncSession, Depends(get_db)]
RedisProvider = Annotated[Redis, Depends(get_redis)]


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
