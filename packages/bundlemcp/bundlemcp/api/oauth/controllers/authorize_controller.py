"""Authorization endpoint + consent screen."""

from typing import Annotated
from urllib.parse import quote

import structlog
from fastapi import Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastmcp.server.auth.redirect_validation import build_client_redirect

from bundlemcp.api.http.controller import Controller
from bundlemcp.api.http.providers import SettingsProvider
from bundlemcp.api.http.route import route
from bundlemcp.api.oauth.oauth_error_response import authorization_error_location
from bundlemcp.api.oauth.pages.form_action_source import form_action_source
from bundlemcp.api.oauth.pages.page_headers import PAGE_HEADERS, page_headers
from bundlemcp.api.oauth.pages.page_templates import PAGE_TEMPLATES
from bundlemcp.api.oauth.providers import (
    AuthorizationServiceProvider,
    CurrentSessionUserProvider,
    PendingAuthorizationsProvider,
)
from bundlemcp.application.errors import AuthorizationRedirectError, InvalidInputError
from bundlemcp.application.oauth_server import AuthorizationRequest, PendingAuthorization
from bundlemcp.domain.oauth.oauth_error_code import OAuthErrorCode

log = structlog.get_logger(__name__)

AuthorizationQuery = Annotated[AuthorizationRequest, Depends(AuthorizationRequest)]


class AuthorizeController(Controller):
    prefix = "/oauth"
    tags = ("oauth",)
    include_in_schema = False

    @staticmethod
    def _code_location(pending: PendingAuthorization, code: str, issuer: str) -> str:
        params = {"code": code}
        if pending.state:
            params["state"] = pending.state
        # A registered redirect URI may carry its own query; the parameters are
        # merged into it, and iss (RFC 9207) is set exactly once.
        return build_client_redirect(pending.redirect_uri, params, iss=issuer)

    @staticmethod
    def _answer_consent(pending: PendingAuthorization, location: str, heading: str) -> Response:
        """Send the browser on to the client once the consent form is answered.

        The consent page's form-action admits the client's redirect URI, so a
        redirect is followed. When that URI could not be admitted, the browser
        would refuse the redirect, so a same-origin page links to it instead.
        """
        if form_action_source(pending.redirect_uri) is not None:
            return RedirectResponse(location, status_code=302)
        html = PAGE_TEMPLATES.get_template("return_to_client.html").render(
            client_name=pending.client_name, heading=heading, location=location
        )
        return HTMLResponse(html, headers=PAGE_HEADERS)

    @route.get("/authorize")
    async def authorize(
        self,
        request: Request,
        query: AuthorizationQuery,
        service: AuthorizationServiceProvider,
        pending_authorizations: PendingAuthorizationsProvider,
        settings: SettingsProvider,
        user: CurrentSessionUserProvider,
    ) -> Response:
        if user is None:
            # needs an authenticated human — bounce through OIDC login.
            # The client must still be genuine before anyone is sent anywhere.
            if not await service.client_is_registered(query):
                raise HTTPException(400, "unknown client or redirect_uri")
            # Build the return URL from public_url, never the incoming Host.
            return_url = f"{settings.public_base}{request.url.path}"
            if request.url.query:
                return_url += f"?{request.url.query}"
            return RedirectResponse(f"/login?next={quote(return_url, safe='')}", status_code=302)

        try:
            pending = await service.validate(query, user)
        except InvalidInputError as exc:
            raise HTTPException(400, str(exc)) from None  # never redirect on client errors
        except AuthorizationRedirectError:
            raise
        if await service.has_consent(pending):
            location = self._code_location(
                pending, await service.issue_code(pending), settings.public_base
            )
            return RedirectResponse(location, status_code=302)

        token = await pending_authorizations.put(pending)  # single-use => CSRF-safe form
        html = PAGE_TEMPLATES.get_template("consent.html").render(
            client_name=pending.client_name,
            endpoint_name=pending.endpoint_name,
            bundle_name=pending.bundle_name,
            scope=pending.scope,
            token=token,
            consent_action="/oauth/consent",
            user_email=user.email or str(user.id),
        )
        # Approve and Deny are answered with a redirect to this client
        headers = page_headers(form_redirect_source=form_action_source(pending.redirect_uri))
        return HTMLResponse(html, headers=headers)

    @route.post("/consent")
    async def consent(
        self,
        service: AuthorizationServiceProvider,
        pending_authorizations: PendingAuthorizationsProvider,
        settings: SettingsProvider,
        user: CurrentSessionUserProvider,
        token: Annotated[str, Form()],
        action: Annotated[str, Form()],
    ) -> Response:
        pending = await pending_authorizations.take(token)
        if pending is None:
            raise HTTPException(400, "consent request expired")
        if user is None or user.id != pending.user_id:
            raise HTTPException(403, "session mismatch")
        if action != "approve":
            denied = AuthorizationRedirectError(
                pending.redirect_uri,
                pending.state,
                OAuthErrorCode.ACCESS_DENIED,
                issuer=settings.public_base,
            )
            return self._answer_consent(
                pending, authorization_error_location(denied), "Access denied"
            )
        await service.grant_consent(pending)
        log.info("oauth.consent_granted", client_id=pending.client_id)
        location = self._code_location(
            pending, await service.issue_code(pending), settings.public_base
        )
        return self._answer_consent(pending, location, "Access granted")
