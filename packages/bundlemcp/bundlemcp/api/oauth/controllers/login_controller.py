"""Admin login through the configured identity provider, and logout."""

import secrets
from typing import Annotated

import structlog
from fastapi import HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse

from bundlemcp.api.http.controller import Controller
from bundlemcp.api.http.providers import SettingsProvider
from bundlemcp.api.http.route import route
from bundlemcp.api.oauth.browser_state.oidc_login_state import OidcLoginState
from bundlemcp.api.oauth.browser_state.post_login_redirect import clamp_post_login_redirect
from bundlemcp.api.oauth.providers import (
    AdminSessionsProvider,
    OidcLoginStatesProvider,
    OidcProviderProvider,
    UserProvisioningServiceProvider,
)
from bundlemcp.api.oauth.session_cookie import SESSION_COOKIE, session_cookie_kwargs
from bundlemcp.application.oauth_server import VerifiedClaims
from bundlemcp.application.settings.settings import Settings
from bundlemcp.domain.access.oidc_error import OidcError
from bundlemcp.domain.sessions.admin_session import AdminSession

log = structlog.get_logger(__name__)


class LoginController(Controller):
    tags = ("auth",)
    include_in_schema = False

    @staticmethod
    def _redirect_uri(settings: Settings) -> str:
        return f"{settings.public_base}/login/callback"

    @route.get("/login")
    async def login(
        self,
        provider: OidcProviderProvider,
        settings: SettingsProvider,
        states: OidcLoginStatesProvider,
        next: Annotated[str, Query()] = "/",  # noqa: A002 - the query parameter is called next
    ) -> Response:
        if provider is None:
            raise HTTPException(503, "no OIDC provider configured")
        nonce = secrets.token_urlsafe(24)
        state = await states.put(
            OidcLoginState(nonce=nonce, next_url=clamp_post_login_redirect(next, settings))
        )
        url = provider.authorize_url(
            state=state, nonce=nonce, redirect_uri=self._redirect_uri(settings)
        )
        return RedirectResponse(url, status_code=302)

    @route.get("/login/callback")
    async def login_callback(
        self,
        provider: OidcProviderProvider,
        settings: SettingsProvider,
        states: OidcLoginStatesProvider,
        provisioning: UserProvisioningServiceProvider,
        admin_sessions: AdminSessionsProvider,
        code: str = "",
        state: str = "",
        error: str = "",
        error_description: str = "",
    ) -> Response:
        login_state = await states.take(state)  # single-use state (CSRF)
        if login_state is None:
            raise HTTPException(400, "invalid or expired state")
        if provider is None:
            raise HTTPException(503, "no OIDC provider configured")
        if error:  # the IdP declined (OIDC Core 3.1.2.6); there is no code to exchange
            raise HTTPException(400, f"login failed: {error} {error_description}".strip())
        try:
            claims = await provider.exchange(
                code=code, redirect_uri=self._redirect_uri(settings), nonce=login_state.nonce
            )
        except OidcError as exc:
            raise HTTPException(400, str(exc)) from None
        user = await provisioning.provision(VerifiedClaims.model_validate(claims.model_dump()))

        session_id = await admin_sessions.create(
            AdminSession(user_id=str(user.id), email=user.email, is_admin=user.is_admin)
        )
        response = RedirectResponse(login_state.next_url or "/", status_code=302)
        response.set_cookie(
            SESSION_COOKIE,
            session_id,
            **session_cookie_kwargs(
                secure=settings.public_base.startswith("https"), max_age=admin_sessions.max_age
            ),
        )
        log.info("admin.login", user_id=str(user.id), is_admin=user.is_admin)
        return response

    @route.post("/logout")
    async def logout(self, request: Request, admin_sessions: AdminSessionsProvider) -> Response:
        session_id = request.cookies.get(SESSION_COOKIE)
        if session_id:
            await admin_sessions.delete(session_id)  # ADM-5
        response = RedirectResponse("/", status_code=302)
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response
