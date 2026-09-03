"""Providers that build a request-scoped service from the shared collaborators.

One per service. A route asks for ``ServerServiceProvider`` and receives a
``ServerService`` bound to this request's unit of work.
"""

from typing import Annotated

from fastapi import Depends, Request

from bundlemcp.providers.collaborators import UnitOfWorkProvider
from bundlemcp.services import (
    AdminSessionService,
    ApiKeyService,
    AuditService,
    AuthService,
    BundleService,
    ConfigService,
    EndpointService,
    ServerService,
    UpstreamOAuthConfigService,
    UserService,
)


def get_server_service(request: Request, uow: UnitOfWorkProvider) -> ServerService:
    return ServerService(uow, discovery=request.app.state.container.discovery)


def get_upstream_oauth_config_service(
    request: Request, uow: UnitOfWorkProvider
) -> UpstreamOAuthConfigService:
    container = request.app.state.container
    return UpstreamOAuthConfigService(
        uow, cipher=container.token_cipher, connections=container.upstream_connections
    )


def get_bundle_service(uow: UnitOfWorkProvider) -> BundleService:
    return BundleService(uow)


def get_endpoint_service(uow: UnitOfWorkProvider) -> EndpointService:
    return EndpointService(uow)


def get_api_key_service(uow: UnitOfWorkProvider) -> ApiKeyService:
    return ApiKeyService(uow)


def get_user_service(uow: UnitOfWorkProvider) -> UserService:
    return UserService(uow)


def get_config_service(uow: UnitOfWorkProvider) -> ConfigService:
    return ConfigService(uow)


def get_audit_service(uow: UnitOfWorkProvider) -> AuditService:
    return AuditService(uow)


def get_auth_service(uow: UnitOfWorkProvider) -> AuthService:
    return AuthService(uow.session)


def get_admin_session_service(request: Request, uow: UnitOfWorkProvider) -> AdminSessionService:
    return AdminSessionService(uow.session, request.app.state.container.admin_sessions)


ServerServiceProvider = Annotated[ServerService, Depends(get_server_service)]
UpstreamOAuthConfigServiceProvider = Annotated[
    UpstreamOAuthConfigService, Depends(get_upstream_oauth_config_service)
]
BundleServiceProvider = Annotated[BundleService, Depends(get_bundle_service)]
EndpointServiceProvider = Annotated[EndpointService, Depends(get_endpoint_service)]
ApiKeyServiceProvider = Annotated[ApiKeyService, Depends(get_api_key_service)]
UserServiceProvider = Annotated[UserService, Depends(get_user_service)]
ConfigServiceProvider = Annotated[ConfigService, Depends(get_config_service)]
AuditServiceProvider = Annotated[AuditService, Depends(get_audit_service)]
AuthServiceProvider = Annotated[AuthService, Depends(get_auth_service)]
AdminSessionServiceProvider = Annotated[AdminSessionService, Depends(get_admin_session_service)]
