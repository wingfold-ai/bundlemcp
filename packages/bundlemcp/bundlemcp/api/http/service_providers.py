"""Providers that build a request-scoped service from the shared collaborators.

One per service. A route asks for ``ServerServiceProvider`` and receives a
``ServerService`` bound to this request's unit of work.
"""

from typing import Annotated

from fastapi import Depends, Request

from bundlemcp.api.http.providers import UnitOfWorkProvider
from bundlemcp.application.auth.admin_session_service import AdminSessionService
from bundlemcp.application.auth.auth_service import AuthService
from bundlemcp.application.auth.caller_resolver import CallerResolver
from bundlemcp.application.management.api_key_service import ApiKeyService
from bundlemcp.application.management.audit_service import AuditService
from bundlemcp.application.management.bundle_service import BundleService
from bundlemcp.application.management.config_service import ConfigService
from bundlemcp.application.management.endpoint_service import EndpointService
from bundlemcp.application.management.server_inspection_service import ServerInspectionService
from bundlemcp.application.management.server_json_importer import ServerJsonImporter
from bundlemcp.application.management.server_service import ServerService
from bundlemcp.application.management.upstream_oauth_config_service import (
    UpstreamOAuthConfigService,
)
from bundlemcp.application.management.user_service import UserService


def get_server_service(request: Request, uow: UnitOfWorkProvider) -> ServerService:
    return ServerService(uow, discovery=request.app.state.container.discovery)


def get_server_inspection_service(
    request: Request, uow: UnitOfWorkProvider
) -> ServerInspectionService:
    container = request.app.state.container
    return ServerInspectionService(
        uow,
        container.upstream_probe,
        container.connection_diagnoser,
        public_base=container.settings.public_base,
    )


def get_server_json_importer() -> ServerJsonImporter:
    return ServerJsonImporter()


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


def get_api_key_service(request: Request, uow: UnitOfWorkProvider) -> ApiKeyService:
    container = request.app.state.container
    return ApiKeyService(uow, hasher=container.secret_hasher, generator=container.secret_generator)


def get_user_service(uow: UnitOfWorkProvider) -> UserService:
    return UserService(uow)


def get_config_service(uow: UnitOfWorkProvider) -> ConfigService:
    return ConfigService(uow)


def get_audit_service(uow: UnitOfWorkProvider) -> AuditService:
    return AuditService(uow)


def get_auth_service(request: Request, uow: UnitOfWorkProvider) -> AuthService:
    container = request.app.state.container
    return AuthService(uow, clock=container.clock, hasher=container.secret_hasher)


def get_admin_session_service(request: Request, uow: UnitOfWorkProvider) -> AdminSessionService:
    return AdminSessionService(uow, request.app.state.container.admin_sessions)


def get_caller_resolver(request: Request, uow: UnitOfWorkProvider) -> CallerResolver:
    container = request.app.state.container
    return CallerResolver(
        uow, container.admin_sessions, clock=container.clock, hasher=container.secret_hasher
    )


ServerServiceProvider = Annotated[ServerService, Depends(get_server_service)]
ServerInspectionServiceProvider = Annotated[
    ServerInspectionService, Depends(get_server_inspection_service)
]
ServerJsonImporterProvider = Annotated[ServerJsonImporter, Depends(get_server_json_importer)]
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
CallerResolverProvider = Annotated[CallerResolver, Depends(get_caller_resolver)]
