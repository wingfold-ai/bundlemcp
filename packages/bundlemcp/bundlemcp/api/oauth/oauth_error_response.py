"""Rendering the protocol's error shapes (RFC 6749 section 5.2)."""

from fastapi import Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastmcp.server.auth.redirect_validation import build_client_redirect

from bundlemcp.application.errors import AuthorizationRedirectError, OAuthError
from bundlemcp.domain.oauth.oauth_error_code import OAuthErrorCode

NO_STORE = {"Cache-Control": "no-store"}


def oauth_error_response(
    code: OAuthErrorCode, description: str = "", *, status: int
) -> JSONResponse:
    body = {"error": code.value}
    if description:
        body["error_description"] = description
    return JSONResponse(body, status_code=status, headers=NO_STORE)


async def oauth_error_handler(request: Request, exc: OAuthError) -> Response:
    return oauth_error_response(exc.code, exc.description, status=exc.status)


def authorization_error_location(exc: AuthorizationRedirectError) -> str:
    """The client's verified redirect URI, carrying the failure as RFC 6749 parameters."""
    params = {"error": exc.code.value}
    if exc.description:
        params["error_description"] = exc.description
    if exc.state:
        params["state"] = exc.state
    # Merged into a redirect URI that may carry its own query; iss is set
    # exactly once on error responses too (AUTH-14).
    return build_client_redirect(exc.redirect_uri, params, iss=exc.issuer)


async def authorization_redirect_handler(
    request: Request, exc: AuthorizationRedirectError
) -> Response:
    """Deliver an authorization failure to the client's verified redirect URI."""
    return RedirectResponse(authorization_error_location(exc), status_code=302)
