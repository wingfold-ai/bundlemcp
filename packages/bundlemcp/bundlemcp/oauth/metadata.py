"""OAuth discovery metadata (OAS-1: RFC 8414 + RFC 9728)."""

from fastapi import APIRouter, HTTPException, Request
from sqlmodel import select

from bundlemcp.models import Endpoint
from bundlemcp.oauth.urls import endpoint_resource, issuer

router = APIRouter(tags=["oauth"])


def _settings(request: Request):
    return request.app.state.settings


@router.get("/.well-known/oauth-authorization-server", include_in_schema=False)
async def authorization_server_metadata(request: Request) -> dict:
    base = issuer(_settings(request))
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "introspection_endpoint": f"{base}/oauth/introspect",
        "revocation_endpoint": f"{base}/oauth/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": [
            "none",
            "client_secret_basic",
            "client_secret_post",
        ],
        "scopes_supported": ["mcp"],
    }


@router.get(
    "/.well-known/oauth-protected-resource/{endpoint_name}/mcp", include_in_schema=False
)
async def protected_resource_metadata(endpoint_name: str, request: Request) -> dict:
    """RFC 9728, per endpoint — the 401 challenge points here (EP-3)."""
    async with request.app.state.session_factory() as db:
        ep = (
            await db.execute(select(Endpoint).where(Endpoint.name == endpoint_name))
        ).scalar_one_or_none()
    if ep is None or not ep.enabled:
        raise HTTPException(404, "unknown resource")
    settings = _settings(request)
    return {
        "resource": endpoint_resource(settings, endpoint_name),
        "authorization_servers": [issuer(settings)],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["mcp"],
    }
