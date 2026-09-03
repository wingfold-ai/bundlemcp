"""Management-API authentication edge.

Credential resolution is framework-free (``bundlemcp.services``); this module
owns the transport concerns the edge decides — the CSRF origin check on
cookie-authenticated mutations and the accept-either 401/403 status policy.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from bundlemcp.oauth.session_cookie import SESSION_COOKIE
from bundlemcp.providers import (
    AdminSessionServiceProvider,
    AuthServiceProvider,
    SettingsProvider,
)
from bundlemcp.services import Principal, PrincipalKind
from bundlemcp.settings import Settings


class ManagementAuth:
    """Accept either an admin session cookie or a service-kind API key."""

    SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

    async def __call__(
        self,
        request: Request,
        auth: AuthServiceProvider,
        admin_sessions: AdminSessionServiceProvider,
        settings: SettingsProvider,
    ) -> Principal:
        admin = await admin_sessions.admin_principal(request.cookies.get(SESSION_COOKIE))
        if admin is not None:
            if request.method not in self.SAFE_METHODS:
                self._check_origin(request, settings)
            return admin
        key = await auth.authenticate_api_key(
            authorization=request.headers.get("authorization"),
            x_api_key=request.headers.get("x-api-key"),
        )
        if key is not None and key.is_service_key:
            return Principal(kind=PrincipalKind.SERVICE, api_key_id=str(key.id))
        if key is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="key is not service-kind (KEY-2)"
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="admin session or service API key required",
        )

    @staticmethod
    def _check_origin(request: Request, settings: Settings) -> None:
        # SEC-4: cookie-authenticated mutations require an Origin/Referer
        # matching the gateway itself or an allowlisted web-app origin
        origin = request.headers.get("origin") or request.headers.get("referer")
        allowed = [settings.public_base] + [o.rstrip("/") for o in settings.web_origins]
        if origin is None or not any(origin.startswith(a) for a in allowed):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF origin check failed (SEC-4)")


ServiceAuthProvider = Annotated[Principal, Depends(ManagementAuth())]
