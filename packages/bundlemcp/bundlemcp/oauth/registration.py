"""Dynamic Client Registration (OAS-2: RFC 7591), rate-limited per IP (SEC-8)."""

import secrets
from urllib.parse import urlparse

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from bundlemcp.models import OAuthClient
from bundlemcp.oauth.urls import issuer
from bundlemcp.security import hash_token

log = structlog.get_logger(__name__)

router = APIRouter(tags=["oauth"])

REGISTRATION_RATE_KEY = "bmcp:rate:dcr:{ip}"
REGISTRATION_RATE_LIMIT = 10  # per window
REGISTRATION_RATE_WINDOW = 3600  # seconds


class RegistrationRequest(BaseModel):
    redirect_uris: list[str] = Field(min_length=1)
    client_name: str | None = None
    token_endpoint_auth_method: str = "none"
    grant_types: list[str] = Field(
        default_factory=lambda: ["authorization_code", "refresh_token"]
    )
    response_types: list[str] = Field(default_factory=lambda: ["code"])
    scope: str = "mcp"


def _validate_redirect_uri(uri: str) -> None:
    parsed = urlparse(uri)
    if parsed.scheme == "https" and parsed.hostname:
        return
    if parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1"):
        return  # native/dev clients
    raise HTTPException(400, {"error": "invalid_redirect_uri", "uri": uri})


async def _check_rate(request: Request) -> None:
    """SEC-8: fail-open on Redis trouble (RATE-6 stance) but loud."""
    ip = request.client.host if request.client else "unknown"
    key = REGISTRATION_RATE_KEY.format(ip=ip)
    try:
        redis = request.app.state.redis
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, REGISTRATION_RATE_WINDOW)
        if count > REGISTRATION_RATE_LIMIT:
            raise HTTPException(429, {"error": "rate_limited"})
    except HTTPException:
        raise
    except Exception:
        log.warning("dcr.rate_limit_unavailable", exc_info=True)


@router.post("/oauth/register", status_code=201, include_in_schema=False)
async def register_client(body: RegistrationRequest, request: Request) -> dict:
    await _check_rate(request)
    for uri in body.redirect_uris:
        _validate_redirect_uri(uri)
    if body.token_endpoint_auth_method not in ("none", "client_secret_basic", "client_secret_post"):
        raise HTTPException(400, {"error": "invalid_client_metadata"})

    client_id = f"bmcp_client_{secrets.token_urlsafe(16)}"
    client_secret: str | None = None
    secret_hash: str | None = None
    if body.token_endpoint_auth_method != "none":
        client_secret = secrets.token_urlsafe(32)
        secret_hash = hash_token(client_secret)

    client = OAuthClient(
        client_id=client_id,
        client_secret_hash=secret_hash,
        client_name=body.client_name,
        redirect_uris=body.redirect_uris,
        grant_types=body.grant_types,
        token_endpoint_auth_method=body.token_endpoint_auth_method,
        scope=body.scope,
    )
    async with request.app.state.session_factory() as db:
        db.add(client)
        await db.commit()

    base = issuer(request.app.state.settings)
    response = {
        "client_id": client_id,
        "client_name": body.client_name,
        "redirect_uris": body.redirect_uris,
        "grant_types": body.grant_types,
        "response_types": body.response_types,
        "token_endpoint_auth_method": body.token_endpoint_auth_method,
        "scope": body.scope,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
    }
    if client_secret is not None:
        response["client_secret"] = client_secret  # shown once (DOM-3)
    return response
