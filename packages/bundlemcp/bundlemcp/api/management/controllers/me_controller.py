"""Caller identity route: lets the web app render login state and the
no-access page without a privileged call.
"""

from fastapi import HTTPException, Request, status

from bundlemcp.api.http.controller import Controller
from bundlemcp.api.http.route import route
from bundlemcp.api.http.service_providers import CallerResolverProvider
from bundlemcp.api.oauth.session_cookie import SESSION_COOKIE
from bundlemcp.application.schemas import MeRead
from bundlemcp.domain.access.api_key import ApiKey
from bundlemcp.domain.access.user import User


class MeController(Controller):
    prefix = "/me"
    tags = ("me",)

    @route.get("")
    async def whoami(self, request: Request, callers: CallerResolverProvider) -> MeRead:
        caller = await callers.resolve(
            session_id=request.cookies.get(SESSION_COOKIE),
            authorization=request.headers.get("authorization"),
            x_api_key=request.headers.get("x-api-key"),
        )
        match caller:
            case User():
                return MeRead(
                    kind="admin" if caller.is_admin else "user",
                    user_id=caller.id,
                    email=caller.email,
                    display_name=caller.display_name,
                    is_admin=caller.is_admin,
                )
            case ApiKey() if caller.is_service_key:
                return MeRead(kind="service", api_key_id=caller.id)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not signed in")
