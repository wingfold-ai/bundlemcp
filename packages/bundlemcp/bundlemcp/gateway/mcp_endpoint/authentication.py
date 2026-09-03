"""Deciding who a caller is, and what to answer when they are nobody."""

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.gateway.composition import BundleView
from bundlemcp.gateway.proxy import client_ip
from bundlemcp.models import CallerIdentity, EndpointAuthMode
from bundlemcp.services import AuthService


def unauthorized(request: Request, endpoint_name: str) -> Response:
    """401 with the challenge + per-endpoint protected-resource metadata (RFC 9728)."""
    base = request.app.state.container.settings.public_base  # DEP-1, not Host header
    metadata = f"{base}/.well-known/oauth-protected-resource/{endpoint_name}/mcp"
    return JSONResponse(
        {"error": "unauthorized"},
        status_code=401,
        headers={"WWW-Authenticate": f'Bearer resource_metadata="{metadata}"'},
    )


async def authenticate(
    request: Request, db: AsyncSession, view: BundleView
) -> CallerIdentity | None:
    """Resolve the caller, trying the endpoint's modes in precedence order oauth > api_key."""
    modes = set(view.endpoint.auth_modes)
    auth_service = AuthService(db)
    authorization = request.headers.get("authorization")
    if EndpointAuthMode.OAUTH in modes:
        oauth = await auth_service.authenticate_oauth_bearer(
            authorization=authorization, endpoint_id=view.endpoint.id
        )
        if oauth is not None:
            return oauth
    if EndpointAuthMode.API_KEY in modes:
        key = await auth_service.authenticate_api_key(
            authorization=authorization,
            x_api_key=request.headers.get("x-api-key"),
        )
        if key is not None:
            if not key.reaches(view.endpoint.id):
                return None  # KEY-2
            return CallerIdentity.with_api_key(key.id)
    if EndpointAuthMode.NONE in modes:
        return CallerIdentity.anonymous()
    return None


async def note_auth_failure(request: Request) -> Response | None:
    """Count an auth failure for the caller IP; 429 once the IP is locked out.

    Gateway-wide, IP-keyed, shared by the MCP edge and the OAuth token endpoint.
    Returns a 429 (+ Retry-After) when the IP is over the threshold, else None
    (the caller then returns its own 401/invalid_client). Fails open on Redis.
    """
    container = request.app.state.container
    limiter = container.auth_failure_limiter
    ip = client_ip(request, container.settings)
    result = await limiter.record_failure(ip)
    if result.allowed:
        return None
    resp = JSONResponse({"error": "too_many_auth_failures"}, status_code=429)
    resp.headers["Retry-After"] = str(result.retry_after)
    return resp
