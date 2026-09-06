"""FastAPI providers for oauth-owned collaborators and the OAuth services.

These live here rather than in the top-level ``bundlemcp.providers`` so that
shared module stays free of oauth imports. Each reads one field off the app's
container or builds a request-scoped service from the unit of work.
"""

from typing import Annotated

from fastapi import Depends, Request

from bundlemcp.gateway.ratelimit import AuthFailureGuard, RateLimiter
from bundlemcp.models import User
from bundlemcp.oauth.oidc.oidc_login_state import OidcLoginState
from bundlemcp.oauth.oidc.oidc_provider import OidcProvider
from bundlemcp.oauth.session_cookie import SESSION_COOKIE
from bundlemcp.oauth.upstream_client import UpstreamTokenStore
from bundlemcp.oauth.upstream_connect_state import UpstreamConnectState
from bundlemcp.providers import (
    AdminSessionServiceProvider,
    RedisProvider,
    SettingsProvider,
    UnitOfWorkProvider,
)
from bundlemcp.services.oauth_server import (
    AuthorizationService,
    ClientMetadataFetcher,
    ClientRegistrationService,
    OAuthTokenService,
    PendingAuthorization,
    TokenIntrospectionService,
    UserProvisioningService,
)
from bundlemcp.store import SingleUseState
from bundlemcp.store.admin_sessions import AdminSessionStore

PENDING_CONSENT_PREFIX = "bmcp:pendingconsent"
PENDING_CONSENT_TTL = 600
OIDC_STATE_PREFIX = "bmcp:oidcstate"
OIDC_STATE_TTL = 600
CONNECT_STATE_PREFIX = "bmcp:upstream-connect"
CONNECT_STATE_TTL = 600


def get_admin_sessions(request: Request) -> AdminSessionStore:
    return request.app.state.container.admin_sessions


def get_upstream_tokens(request: Request) -> UpstreamTokenStore | None:
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


def get_pending_authorizations(redis: RedisProvider) -> SingleUseState[PendingAuthorization]:
    return SingleUseState(
        redis,
        prefix=PENDING_CONSENT_PREFIX,
        ttl_seconds=PENDING_CONSENT_TTL,
        model=PendingAuthorization,
    )


def get_oidc_login_states(redis: RedisProvider) -> SingleUseState[OidcLoginState]:
    return SingleUseState(
        redis, prefix=OIDC_STATE_PREFIX, ttl_seconds=OIDC_STATE_TTL, model=OidcLoginState
    )


def get_connect_states(redis: RedisProvider) -> SingleUseState[UpstreamConnectState]:
    return SingleUseState(
        redis,
        prefix=CONNECT_STATE_PREFIX,
        ttl_seconds=CONNECT_STATE_TTL,
        model=UpstreamConnectState,
    )


def get_token_service(uow: UnitOfWorkProvider) -> OAuthTokenService:
    return OAuthTokenService(uow)


def get_introspection_service(
    uow: UnitOfWorkProvider, settings: SettingsProvider
) -> TokenIntrospectionService:
    return TokenIntrospectionService(uow, public_base=settings.public_base)


def get_client_metadata_fetcher(request: Request) -> ClientMetadataFetcher:
    return request.app.state.container.client_metadata


ClientMetadataFetcherProvider = Annotated[
    ClientMetadataFetcher, Depends(get_client_metadata_fetcher)
]


def get_authorization_service(
    uow: UnitOfWorkProvider, settings: SettingsProvider, fetcher: ClientMetadataFetcherProvider
) -> AuthorizationService:
    return AuthorizationService(uow, public_base=settings.public_base, client_metadata=fetcher)


def get_client_registration_service(
    uow: UnitOfWorkProvider, settings: SettingsProvider
) -> ClientRegistrationService:
    return ClientRegistrationService(uow, public_base=settings.public_base)


def get_user_provisioning_service(
    uow: UnitOfWorkProvider, settings: SettingsProvider
) -> UserProvisioningService:
    return UserProvisioningService(uow, admin_emails=settings.admin_emails)


AdminSessionsProvider = Annotated[AdminSessionStore, Depends(get_admin_sessions)]
UpstreamTokensProvider = Annotated[UpstreamTokenStore | None, Depends(get_upstream_tokens)]
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
