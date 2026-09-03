"""Providers that build a request-scoped service from the shared collaborators.

One per resource, mirroring ``bundlemcp.services``. A route asks for
``ServerServiceProvider`` and receives a ``ServerService`` bound to this
request's database session.
"""

from typing import Annotated

from fastapi import Depends, Request

from bundlemcp.providers.collaborators import DbProvider, RedisProvider
from bundlemcp.services import (
    ApiKeyService,
    AuditService,
    BundleService,
    ConfigService,
    EndpointService,
    ServerService,
    UserService,
)


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
