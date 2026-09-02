"""FastAPI providers for oauth-owned collaborators.

These live here rather than in ``api/providers.py`` so the shared provider
module stays free of oauth imports: ``oauth.oidc`` re-exports its router, and a
provider module importing it would close an import cycle back through the
routes that consume the providers.
"""

from typing import Annotated

from fastapi import Depends, Request

from bundlemcp.oauth.adminsessions import AdminSessionStore
from bundlemcp.oauth.upstream_client import UpstreamTokenStore


def get_admin_sessions(request: Request) -> AdminSessionStore:
    return request.app.state.admin_sessions


def get_upstream_tokens(request: Request) -> UpstreamTokenStore | None:
    """None when no token encryption keys are configured."""
    return request.app.state.upstream_tokens


AdminSessionsProvider = Annotated[AdminSessionStore, Depends(get_admin_sessions)]
UpstreamTokensProvider = Annotated[UpstreamTokenStore | None, Depends(get_upstream_tokens)]
