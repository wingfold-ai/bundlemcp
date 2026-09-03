"""FastAPI providers for oauth-owned collaborators.

These live here rather than in the top-level ``bundlemcp.providers`` so that
shared module stays free of oauth imports. Each reads one field off the app's
container.
"""

from typing import Annotated

from fastapi import Depends, Request

from bundlemcp.gateway.ratelimit import AuthFailureLimiter
from bundlemcp.oauth.oidc.oidc_provider import OidcProvider
from bundlemcp.oauth.upstream_client import UpstreamTokenStore
from bundlemcp.store.admin_sessions import AdminSessionStore


def get_admin_sessions(request: Request) -> AdminSessionStore:
    return request.app.state.container.admin_sessions


def get_upstream_tokens(request: Request) -> UpstreamTokenStore | None:
    """None when no token encryption keys are configured."""
    return request.app.state.container.upstream_tokens


def get_auth_failure_limiter(request: Request) -> AuthFailureLimiter:
    return request.app.state.container.auth_failure_limiter


def get_oidc_provider(request: Request) -> OidcProvider | None:
    """None when no OIDC issuer is configured; routes must reject in that case."""
    return request.app.state.container.oidc_provider


AdminSessionsProvider = Annotated[AdminSessionStore, Depends(get_admin_sessions)]
UpstreamTokensProvider = Annotated[UpstreamTokenStore | None, Depends(get_upstream_tokens)]
AuthFailureLimiterProvider = Annotated[AuthFailureLimiter, Depends(get_auth_failure_limiter)]
OidcProviderProvider = Annotated[OidcProvider | None, Depends(get_oidc_provider)]
