"""Rendering the protocol's error shapes (RFC 6749 section 5.2)."""

from fastapi import Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastmcp.server.auth.redirect_validation import build_client_redirect

from bundlemcp.application.errors import AuthorizationRedirectError, OAuthError

NO_STORE = {"Cache-Control": "no-store"}


def oauth_error_response(error: str, description: str = "", *, status: int = 400) -> JSONResponse:
    body = {"error": error}
    if description:
        body["error_description"] = description
    return JSONResponse(body, status_code=status, headers=NO_STORE)


async def oauth_error_handler(request: Request, exc: OAuthError) -> Response:
    return oauth_error_response(exc.error, exc.description, status=exc.status)


async def authorization_redirect_handler(
    request: Request, exc: AuthorizationRedirectError
) -> Response:
    """Deliver an authorization failure to the client's verified redirect URI."""
    params = {"error": exc.error}
    if exc.description:
        params["error_description"] = exc.description
    if exc.state:
        params["state"] = exc.state
    # Merged into a redirect URI that may carry its own query; iss is set
    # exactly once on error responses too (OAS-14).
    return RedirectResponse(
        build_client_redirect(exc.redirect_uri, params, iss=exc.issuer), status_code=302
    )
