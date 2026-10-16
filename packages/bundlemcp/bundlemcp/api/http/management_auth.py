"""Management-API authentication edge.

Credential resolution is framework-free (``bundlemcp.application``); this module
owns the transport concerns the edge decides — the CSRF origin check on
cookie-authenticated mutations and the status policy: 401 when no valid session
or key was presented, 403 when the caller is known but may not manage the
gateway (a signed-in user who is not an admin, or an endpoint-kind key).
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from bundlemcp.api.http.log_context import bind_request_fields
from bundlemcp.api.http.providers import SettingsProvider
from bundlemcp.api.http.service_providers import CallerResolverProvider
from bundlemcp.api.oauth.session_cookie import SESSION_COOKIE
from bundlemcp.application.settings.settings import Settings
from bundlemcp.domain.access.api_key import ApiKey
from bundlemcp.domain.access.principal import Principal
from bundlemcp.domain.access.principal_kind import PrincipalKind
from bundlemcp.domain.access.user import User


class ManagementAuth:
    """Accept either an admin session cookie or a service-kind API key."""

    SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

    async def __call__(
        self, request: Request, callers: CallerResolverProvider, settings: SettingsProvider
    ) -> Principal:
        caller = await callers.resolve(
            session_id=request.cookies.get(SESSION_COOKIE),
            authorization=request.headers.get("authorization"),
            x_api_key=request.headers.get("x-api-key"),
        )
        match caller:
            case User(is_admin=True):
                if request.method not in self.SAFE_METHODS:
                    self._check_origin(request, settings)
                bind_request_fields(auth_method="admin_session", user_id=str(caller.id))
                return self._remember(
                    request, Principal(kind=PrincipalKind.ADMIN, user_id=str(caller.id))
                )
            case ApiKey() if caller.is_service_key:
                bind_request_fields(auth_method="service_key", api_key_id=str(caller.id))
                return self._remember(
                    request, Principal(kind=PrincipalKind.SERVICE, api_key_id=str(caller.id))
                )
            case ApiKey():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="key is not service-kind (AUTH-23)",
                )
            case User():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="signed in, but not an administrator (AUTH-17)",
                )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="admin session or service API key required",
        )

    @staticmethod
    def _remember(request: Request, principal: Principal) -> Principal:
        """Keep the caller on the request, for the few handlers whose rule depends on who it is."""
        request.state.principal = principal
        return principal

    @staticmethod
    def _check_origin(request: Request, settings: Settings) -> None:
        require_same_site_origin(request, settings)


def require_same_site_origin(request: Request, settings: Settings) -> None:
    """403 unless a cookie-authenticated mutation comes from the gateway or an allowed web app.

    An Origin is an origin and must match exactly; a Referer is a URL and must
    sit under one. A plain prefix test would let
    https://gw.example.com.evil.test through.
    """
    allowed = [settings.public_base] + [o.rstrip("/") for o in settings.web_origins]
    origin = request.headers.get("origin")
    if origin is not None:
        if origin.rstrip("/") in allowed:
            return
    else:
        referer = request.headers.get("referer")
        if referer is not None and any(
            referer == a or referer.startswith(a + "/") for a in allowed
        ):
            return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF origin check failed (SEC-4)")


ServiceAuthProvider = Annotated[Principal, Depends(ManagementAuth())]


def current_principal(request: Request) -> Principal:
    """The caller ManagementAuth admitted; only reachable behind a management controller."""
    return request.state.principal


PrincipalProvider = Annotated[Principal, Depends(current_principal)]
