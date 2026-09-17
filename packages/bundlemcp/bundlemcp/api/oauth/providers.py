"""FastAPI providers for oauth-owned collaborators and the OAuth services.

These live here rather than in ``bundlemcp.api.http.providers`` so that
shared module stays free of oauth imports. Each reads one field off the app's
container or builds a request-scoped service from the unit of work. What the
services are built from — the grants served, the ways a client may identify
itself, the token lifetimes — is read from the container: the composition
root and runtime configuration decide it, this module only instantiates it
for the request's transaction.
"""

from typing import Annotated

from fastapi import Depends, Request

from bundlemcp.api.http.auth_failure_guard import AuthFailureGuard
from bundlemcp.api.http.providers import SettingsProvider, UnitOfWorkProvider
from bundlemcp.api.http.service_providers import AdminSessionServiceProvider, AuthServiceProvider
from bundlemcp.api.oauth.browser_state.oidc_login_state import OidcLoginState
from bundlemcp.api.oauth.browser_state.upstream_connect_state import UpstreamConnectState
from bundlemcp.api.oauth.session_cookie import SESSION_COOKIE
from bundlemcp.application.contracts.identity.oidc_provider import OidcProvider
from bundlemcp.application.contracts.live_state.admin_session_store import AdminSessionStore
from bundlemcp.application.contracts.live_state.rate_limiter import RateLimiter
from bundlemcp.application.contracts.live_state.single_use_state import SingleUseState
from bundlemcp.application.oauth_server import (
    AuthorizationCodeIssuer,
    AuthorizationService,
    ClientRegistrationService,
    ClientResolver,
    ConsentService,
    OAuthClientAuthenticator,
    OAuthTokenService,
    PendingAuthorization,
    TokenIntrospectionService,
    TokenIssuer,
    UserProvisioningService,
)
from bundlemcp.application.upstream_oauth.upstream_token_service import UpstreamTokenService
from bundlemcp.domain.access.user import User


def get_admin_sessions(request: Request) -> AdminSessionStore:
    return request.app.state.container.admin_sessions


def get_upstream_tokens(request: Request) -> UpstreamTokenService | None:
    """None when no token encryption keys are configured."""
    return request.app.state.container.upstream_tokens


def get_auth_failure_guard(request: Request) -> AuthFailureGuard:
    return request.app.state.container.auth_failure_guard


def get_rate_limiter(request: Request) -> RateLimiter:
    return request.app.state.container.rate_limiter


def get_oidc_provider(request: Request) -> OidcProvider | None:
    """None when no OIDC issuer is configured; routes must reject in that case."""
    return request.app.state.container.oidc_provider


async def get_current_session_user(
    request: Request, admin_sessions: AdminSessionServiceProvider
) -> User | None:
    """The signed-in browser user, admin or not; None without a valid session cookie."""
    return await admin_sessions.session_user(request.cookies.get(SESSION_COOKIE))


def get_pending_authorizations(request: Request) -> SingleUseState[PendingAuthorization]:
    return request.app.state.container.pending_authorizations


def get_oidc_login_states(request: Request) -> SingleUseState[OidcLoginState]:
    return request.app.state.container.oidc_login_states


def get_connect_states(request: Request) -> SingleUseState[UpstreamConnectState]:
    return request.app.state.container.connect_states


async def get_token_service(request: Request, uow: UnitOfWorkProvider) -> OAuthTokenService:
    container = request.app.state.container
    clock, hasher = container.clock, container.secret_hasher
    issuer = TokenIssuer(
        uow,
        await container.runtime_config.token_policy(),
        clock=clock,
        generator=container.secret_generator,
        hasher=hasher,
    )
    return OAuthTokenService(
        uow,
        clients=OAuthClientAuthenticator(uow, hasher),
        grants=[build(uow, issuer, clock, hasher) for build in container.token_grants],
        clock=clock,
        hasher=hasher,
    )


def get_introspection_service(
    request: Request, uow: UnitOfWorkProvider, auth: AuthServiceProvider, settings: SettingsProvider
) -> TokenIntrospectionService:
    container = request.app.state.container
    return TokenIntrospectionService(
        uow,
        auth=auth,
        clock=container.clock,
        hasher=container.secret_hasher,
        public_base=settings.public_base,
    )


async def get_authorization_service(
    request: Request, uow: UnitOfWorkProvider, settings: SettingsProvider
) -> AuthorizationService:
    container = request.app.state.container
    return AuthorizationService(
        uow,
        public_base=settings.public_base,
        clients=ClientResolver([build(uow) for build in container.client_sources]),
        consents=ConsentService(uow),
        codes=AuthorizationCodeIssuer(
            uow,
            await container.runtime_config.token_policy(),
            clock=container.clock,
            generator=container.secret_generator,
            hasher=container.secret_hasher,
        ),
    )


def get_client_registration_service(
    request: Request, uow: UnitOfWorkProvider, settings: SettingsProvider
) -> ClientRegistrationService:
    container = request.app.state.container
    return ClientRegistrationService(
        uow,
        public_base=settings.public_base,
        generator=container.secret_generator,
        hasher=container.secret_hasher,
    )


def get_user_provisioning_service(
    uow: UnitOfWorkProvider, settings: SettingsProvider
) -> UserProvisioningService:
    return UserProvisioningService(uow, admin_emails=settings.admin_emails)


AdminSessionsProvider = Annotated[AdminSessionStore, Depends(get_admin_sessions)]
UpstreamTokensProvider = Annotated[UpstreamTokenService | None, Depends(get_upstream_tokens)]
AuthFailureGuardProvider = Annotated[AuthFailureGuard, Depends(get_auth_failure_guard)]
RateLimiterProvider = Annotated[RateLimiter, Depends(get_rate_limiter)]
OidcProviderProvider = Annotated[OidcProvider | None, Depends(get_oidc_provider)]
CurrentSessionUserProvider = Annotated[User | None, Depends(get_current_session_user)]
PendingAuthorizationsProvider = Annotated[
    SingleUseState[PendingAuthorization], Depends(get_pending_authorizations)
]
OidcLoginStatesProvider = Annotated[SingleUseState[OidcLoginState], Depends(get_oidc_login_states)]
ConnectStatesProvider = Annotated[SingleUseState[UpstreamConnectState], Depends(get_connect_states)]
TokenServiceProvider = Annotated[OAuthTokenService, Depends(get_token_service)]
IntrospectionServiceProvider = Annotated[
    TokenIntrospectionService, Depends(get_introspection_service)
]
AuthorizationServiceProvider = Annotated[AuthorizationService, Depends(get_authorization_service)]
ClientRegistrationServiceProvider = Annotated[
    ClientRegistrationService, Depends(get_client_registration_service)
]
UserProvisioningServiceProvider = Annotated[
    UserProvisioningService, Depends(get_user_provisioning_service)
]
