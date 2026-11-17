"""Admin login through the configured identity provider, and logout."""

import secrets
from typing import Annotated

import structlog
from fastapi import HTTPException, Query, Request, Response
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse, RedirectResponse

from bundlemcp.api.http.controller import Controller
from bundlemcp.api.http.providers import SettingsProvider
from bundlemcp.api.http.route import route
from bundlemcp.api.oauth.browser_state.oidc_login_state import OidcLoginState
from bundlemcp.api.oauth.browser_state.post_login_redirect import clamp_post_login_redirect
from bundlemcp.api.oauth.login_binding_cookie import (
    login_binding_cookie_kwargs,
    login_binding_cookie_name,
)
from bundlemcp.api.oauth.pages.auth_page import AuthPage
from bundlemcp.api.oauth.providers import (
    AdminSessionsProvider,
    AuthPagesProvider,
    OidcLoginStatesProvider,
    OidcProviderProvider,
    UserProvisioningServiceProvider,
)
from bundlemcp.api.oauth.session_cookie import SESSION_COOKIE, session_cookie_kwargs
from bundlemcp.application.oauth_server import VerifiedClaims
from bundlemcp.application.settings.settings import Settings
from bundlemcp.domain.access.oidc_error import OidcError
from bundlemcp.domain.access.oidc_unavailable import OidcUnavailable
from bundlemcp.domain.oauth.pkce import PkcePair
from bundlemcp.domain.sessions.admin_session import AdminSession
from bundlemcp.domain.shared.secrets import hash_token, tokens_equal

log = structlog.get_logger(__name__)


class LoginController(Controller):
    tags = ("auth",)
    include_in_schema = False

    @staticmethod
    def _redirect_uri(settings: Settings) -> str:
        return f"{settings.public_base}/login/callback"

    @staticmethod
    def _secure(settings: Settings) -> bool:
        return settings.public_base.startswith("https")

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
        pkce = PkcePair.generate()
        browser_binding = secrets.token_urlsafe(32)
        state = await states.put(
            OidcLoginState(
                nonce=nonce,
                code_verifier=pkce.verifier,
                next_url=clamp_post_login_redirect(next, settings),
                browser_binding_hash=hash_token(browser_binding),
            )
        )
        try:
            url = await provider.authorize_url(
                state=state,
                nonce=nonce,
                redirect_uri=self._redirect_uri(settings),
                code_challenge=pkce.challenge,
            )
        except OidcUnavailable as exc:
            raise _unavailable(exc) from None
        response = RedirectResponse(url, status_code=302)
        secure = self._secure(settings)
        response.set_cookie(
            login_binding_cookie_name(secure),
            browser_binding,
            **login_binding_cookie_kwargs(secure),
        )
        return response

    @route.get("/login/callback")
    async def login_callback(
        self,
        request: Request,
        provider: OidcProviderProvider,
        settings: SettingsProvider,
        states: OidcLoginStatesProvider,
        provisioning: UserProvisioningServiceProvider,
        admin_sessions: AdminSessionsProvider,
        pages: AuthPagesProvider,
        code: str = "",
        state: str = "",
        error: str = "",
        error_description: str = "",
    ) -> Response:
        secure = self._secure(settings)
        cookie_name = login_binding_cookie_name(secure)
        try:
            response = await self._finish_login(
                request.cookies.get(cookie_name),
                provider=provider,
                settings=settings,
                states=states,
                provisioning=provisioning,
                admin_sessions=admin_sessions,
                pages=pages,
                code=code,
                state=state,
                error=error,
                error_description=error_description,
            )
        except HTTPException as exc:
            response = await http_exception_handler(request, exc)
        # the binding is spent whatever the outcome; a retry starts a fresh login
        response.delete_cookie(cookie_name, path="/", secure=secure, httponly=True, samesite="lax")
        return response

    async def _finish_login(
        self,
        browser_binding: str | None,
        *,
        provider: OidcProviderProvider,
        settings: SettingsProvider,
        states: OidcLoginStatesProvider,
        provisioning: UserProvisioningServiceProvider,
        admin_sessions: AdminSessionsProvider,
        pages: AuthPagesProvider,
        code: str,
        state: str,
        error: str,
        error_description: str,
    ) -> Response:
        # cheapest check first: a browser that never started this login holds no
        # binding, and is refused without touching the live store
        if not browser_binding:
            raise HTTPException(400, "login was not started in this browser")
        login_state = await states.take(state)  # single-use state (CSRF)
        if login_state is None:
            raise HTTPException(400, "invalid or expired state")
        if not tokens_equal(hash_token(browser_binding), login_state.browser_binding_hash):
            raise HTTPException(400, "login was not started in this browser")
        if provider is None:
            raise HTTPException(503, "no OIDC provider configured")
        if error:  # the IdP declined (OIDC Core 3.1.2.6); there is no code to exchange
            raise HTTPException(400, f"login failed: {error} {error_description}".strip())
        try:
            claims = await provider.exchange(
                code=code,
                redirect_uri=self._redirect_uri(settings),
                nonce=login_state.nonce,
                code_verifier=login_state.code_verifier,
            )
        except OidcUnavailable as exc:
            raise _unavailable(exc) from None
        except OidcError as exc:
            raise HTTPException(400, str(exc)) from None
        user = await provisioning.provision(VerifiedClaims.model_validate(claims.model_dump()))
        if not user.is_active:
            # the authorize flow signs people in here too, so it is refused the same way
            log.info("admin.login_refused_deactivated", user_id=str(user.id))
            html = pages.render(AuthPage.ACCOUNT_DEACTIVATED)
            return HTMLResponse(html, status_code=403, headers=pages.headers())

        session_id = await admin_sessions.create(
            AdminSession(user_id=str(user.id), email=user.email, is_admin=user.is_admin)
        )
        response = RedirectResponse(login_state.next_url or "/", status_code=302)
        response.set_cookie(
            SESSION_COOKIE,
            session_id,
            **session_cookie_kwargs(secure=self._secure(settings), max_age=admin_sessions.max_age),
        )
        log.info("admin.login", user_id=str(user.id), is_admin=user.is_admin)
        return response

    @route.post("/logout")
    async def logout(self, request: Request, admin_sessions: AdminSessionsProvider) -> Response:
        session_id = request.cookies.get(SESSION_COOKIE)
        if session_id:
            await admin_sessions.delete(session_id)
        response = RedirectResponse("/", status_code=302)
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response


def _unavailable(exc: OidcUnavailable) -> HTTPException:
    # the IdP is not reachable yet; the gateway keeps retrying discovery.
    log.warning("admin.login_unavailable", retry_after=exc.retry_after)
    return HTTPException(503, str(exc), headers={"Retry-After": str(exc.retry_after)})
