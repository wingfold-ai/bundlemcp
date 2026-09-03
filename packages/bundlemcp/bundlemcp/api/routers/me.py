"""Caller identity route: lets the web app render login state and the
no-access page without a privileged call.
"""

from fastapi import APIRouter, HTTPException, Request, status

from bundlemcp.oauth.session_cookie import SESSION_COOKIE
from bundlemcp.providers import AdminSessionServiceProvider, AuthServiceProvider
from bundlemcp.schemas import MeRead

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
async def whoami(
    request: Request, auth: AuthServiceProvider, admin_sessions: AdminSessionServiceProvider
) -> MeRead:
    user = await admin_sessions.session_user(request.cookies.get(SESSION_COOKIE))
    if user is not None:
        return MeRead(
            kind="admin" if user.is_admin else "user",
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            is_admin=user.is_admin,
        )
    key = await auth.authenticate_api_key(
        authorization=request.headers.get("authorization"),
        x_api_key=request.headers.get("x-api-key"),
    )
    if key is not None and key.is_service_key:
        return MeRead(kind="service", api_key_id=key.id)
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not signed in")
