"""Management-API authentication edge.

Credential resolution is framework-free (``bundlemcp.services.AuthService``);
this module owns the transport concerns the edge decides — the CSRF origin check
on cookie-authenticated mutations and the accept-either 401/403 status policy.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from bundlemcp.api.providers import DbProvider
from bundlemcp.models import ApiKeyKind
from bundlemcp.services import AuthService, Principal


def get_auth_service(request: Request, db: DbProvider) -> AuthService:
    return AuthService(db, admin_sessions=getattr(request.app.state, "admin_sessions", None))


AuthServiceProvider = Annotated[AuthService, Depends(get_auth_service)]


class ManagementAuth:
    """Accept either an admin session cookie or a service-kind API key."""

    SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

    async def __call__(self, request: Request, auth: AuthServiceProvider) -> Principal:
        from bundlemcp.oauth.adminsessions import SESSION_COOKIE

        admin = await auth.admin_principal(request.cookies.get(SESSION_COOKIE))
        if admin is not None:
            if request.method not in self.SAFE_METHODS:
                # SEC-4: cookie-authenticated mutations require an Origin/Referer
                # matching the gateway itself or an allowlisted web-app origin
                origin = request.headers.get("origin") or request.headers.get("referer")
                settings = request.app.state.settings
                allowed = [str(settings.public_url).rstrip("/")] + [
                    o.rstrip("/") for o in settings.web_origins
                ]
                if origin is None or not any(origin.startswith(a) for a in allowed):
                    raise HTTPException(
                        status.HTTP_403_FORBIDDEN, "CSRF origin check failed (SEC-4)"
                    )
            return admin
        key = await auth.authenticate_api_key(
            authorization=request.headers.get("authorization"),
            x_api_key=request.headers.get("x-api-key"),
        )
        if key is not None and key.kind == ApiKeyKind.SERVICE:
            return Principal(kind="service", api_key_id=str(key.id))
        if key is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="key is not service-kind (KEY-2)"
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="admin session or service API key required",
        )


ServiceAuthProvider = Annotated[Principal, Depends(ManagementAuth())]
