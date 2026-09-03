"""FastAPI providers for oauth-owned collaborators.

These live here rather than in the top-level ``bundlemcp.providers`` so that
shared module stays free of oauth imports: ``oauth.oidc`` re-exports its router,
and a provider module importing it would close an import cycle back through the
routes that consume the providers.

``AuthFailureLimiterProvider`` is here for the same reason it is oauth-owned:
the token endpoint is its only consumer.
"""

from typing import Annotated

from fastapi import Depends, Request

from bundlemcp.gateway.ratelimit import AuthFailureLimiter
from bundlemcp.oauth.adminsessions import AdminSessionStore
from bundlemcp.oauth.upstream_client import UpstreamTokenStore


def get_admin_sessions(request: Request) -> AdminSessionStore:
    return request.app.state.admin_sessions


def get_upstream_tokens(request: Request) -> UpstreamTokenStore | None:
    """None when no token encryption keys are configured."""
    return request.app.state.upstream_tokens


def get_auth_failure_limiter(request: Request) -> AuthFailureLimiter:
    return request.app.state.auth_failure_limiter


AdminSessionsProvider = Annotated[AdminSessionStore, Depends(get_admin_sessions)]
UpstreamTokensProvider = Annotated[UpstreamTokenStore | None, Depends(get_upstream_tokens)]
AuthFailureLimiterProvider = Annotated[AuthFailureLimiter, Depends(get_auth_failure_limiter)]
