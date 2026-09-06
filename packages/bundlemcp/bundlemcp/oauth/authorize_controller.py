"""Authorization endpoint + consent screen."""

from typing import Annotated
from urllib.parse import quote

import structlog
from fastapi import Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastmcp.server.auth.redirect_validation import build_client_redirect

from bundlemcp.http import Controller, route
from bundlemcp.oauth.page_headers import PAGE_HEADERS
from bundlemcp.oauth.page_templates import PAGE_TEMPLATES
from bundlemcp.oauth.providers import (
    AuthorizationServiceProvider,
    CurrentSessionUserProvider,
    PendingAuthorizationsProvider,
)
from bundlemcp.providers import SettingsProvider
from bundlemcp.services.errors import AuthorizationRedirectError, InvalidInputError
from bundlemcp.services.oauth_server import AuthorizationRequest, PendingAuthorization

log = structlog.get_logger(__name__)

AuthorizationQuery = Annotated[AuthorizationRequest, Depends(AuthorizationRequest)]


class AuthorizeController(Controller):
    prefix = "/oauth"
    tags = ("oauth",)
    include_in_schema = False

    @staticmethod
    def _code_redirect(pending: PendingAuthorization, code: str, issuer: str) -> RedirectResponse:
        params = {"code": code}
        if pending.state:
            params["state"] = pending.state
        # A registered redirect URI may carry its own query; the parameters are
        # merged into it, and iss (OAS-14, RFC 9207) is set exactly once.
        return RedirectResponse(
            build_client_redirect(pending.redirect_uri, params, iss=issuer), status_code=302
        )

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
            # OAS-3: needs an authenticated human — bounce through OIDC login.
            # The client must still be genuine before anyone is sent anywhere.
            if not await service.client_is_registered(query):
                raise HTTPException(400, "unknown client or redirect_uri")
            # Build the return URL from public_url (DEP-1), never the incoming Host.
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
            return self._code_redirect(
                pending, await service.issue_code(pending), settings.public_base
            )

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
        return HTMLResponse(html, headers=PAGE_HEADERS)

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
            raise AuthorizationRedirectError(
                pending.redirect_uri, pending.state, "access_denied", issuer=settings.public_base
            )
        await service.grant_consent(pending)
        log.info("oauth.consent_granted", client_id=pending.client_id)
        return self._code_redirect(pending, await service.issue_code(pending), settings.public_base)
