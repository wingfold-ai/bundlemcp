"""Token endpoint, introspection, revocation."""

import asyncio
import base64
import hashlib
import uuid
from datetime import timedelta

import structlog
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlmodel import select

from bundlemcp.crypto import (
    ACCESS_TOKEN_PREFIX,
    REFRESH_TOKEN_PREFIX,
    generate_token,
    hash_token,
    tokens_equal,
)
from bundlemcp.gateway.proxy import client_ip
from bundlemcp.gateway.ratelimit import AuthFailureLimiter
from bundlemcp.models import (
    ApiKeyKind,
    Endpoint,
    OAuthAccessToken,
    OAuthAuthorizationCode,
    OAuthClient,
    User,
    utcnow,
)
from bundlemcp.oauth.providers import AuthFailureLimiterProvider
from bundlemcp.oauth.urls import endpoint_resource
from bundlemcp.providers import (
    SessionFactoryProvider,
    SettingsProvider,
)
from bundlemcp.services import AuthService
from bundlemcp.settings import Settings

log = structlog.get_logger(__name__)

router = APIRouter(tags=["oauth"])

ACCESS_TOKEN_TTL = timedelta(hours=1)  # OAS-4 (runtime Config later)
REFRESH_TOKEN_TTL = timedelta(days=7)


def _token_error(error: str, description: str = "", status: int = 400) -> JSONResponse:
    body = {"error": error}
    if description:
        body["error_description"] = description
    return JSONResponse(body, status_code=status, headers={"Cache-Control": "no-store"})


def _verify_pkce(verifier: str, challenge: str) -> bool:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == challenge


async def _note_token_auth_failure(
    request: Request, limiter: AuthFailureLimiter | None, settings: Settings
) -> JSONResponse | None:
    """Count an OAuth-token credential failure per client IP.

    Returns a 429 (+ Retry-After) once the IP is locked out, else None so the
    caller returns its own invalid_client/invalid_grant. Fails open on Redis.
    """
    if limiter is None:
        return None
    result = await limiter.record_failure(client_ip(request, settings))
    if result.allowed:
        return None
    resp = _token_error("too_many_requests", "too many authentication failures", status=429)
    resp.headers["Retry-After"] = str(result.retry_after)
    return resp


async def _invalid_grant(
    request: Request,
    limiter: AuthFailureLimiter | None,
    settings: Settings,
    description: str = "",
) -> JSONResponse:
    """A failed grant is a credential-scan signal → count it, maybe 429."""
    locked = await _note_token_auth_failure(request, limiter, settings)
    return locked if locked is not None else _token_error("invalid_grant", description)


async def _authenticate_client(request: Request, db, client_id: str, client_secret: str | None):
    """Public clients: client_id only. Confidential: secret via basic or post."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(auth[6:]).decode()
            client_id, _, client_secret = decoded.partition(":")
        except Exception:
            return None
    client = (
        await db.execute(select(OAuthClient).where(OAuthClient.client_id == client_id))
    ).scalar_one_or_none()
    if client is None:
        return None
    if client.token_endpoint_auth_method != "none":
        if not client_secret or client.client_secret_hash is None:
            return None
        if not tokens_equal(hash_token(client_secret), client.client_secret_hash):
            return None
    return client


def _issue_pair(client_id: str, user_id: uuid.UUID, endpoint_id: uuid.UUID, scope: str):
    access = generate_token(ACCESS_TOKEN_PREFIX)
    refresh = generate_token(REFRESH_TOKEN_PREFIX)
    row = OAuthAccessToken(
        access_token_hash=hash_token(access),
        refresh_token_hash=hash_token(refresh),
        client_id=client_id,
        user_id=user_id,
        endpoint_id=endpoint_id,
        scope=scope,
        expires_at=utcnow() + ACCESS_TOKEN_TTL,
        refresh_expires_at=utcnow() + REFRESH_TOKEN_TTL,
    )
    return access, refresh, row


def _token_response(access: str, refresh: str, scope: str) -> JSONResponse:
    return JSONResponse(
        {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": int(ACCESS_TOKEN_TTL.total_seconds()),
            "refresh_token": refresh,
            "scope": scope,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.post("/oauth/token", include_in_schema=False)
async def token(  # noqa: PLR0911 - protocol branching
    request: Request,
    session_factory: SessionFactoryProvider,
    settings: SettingsProvider,
    limiter: AuthFailureLimiterProvider,
    grant_type: str = Form(...),
    code: str = Form(None),
    redirect_uri: str = Form(None),
    code_verifier: str = Form(None),
    refresh_token: str = Form(None),
    client_id: str = Form(None),
    client_secret: str = Form(None),
):
    async with session_factory() as db:
        client = await _authenticate_client(request, db, client_id or "", client_secret)
        if client is None:
            locked = await _note_token_auth_failure(request, limiter, settings)  # RATE-5
            return locked if locked is not None else _token_error("invalid_client", status=401)
        client.last_used_at = utcnow()  # SEC-8 stale-client purge signal
        db.add(client)

        if grant_type == "authorization_code":
            if not code or not code_verifier:
                return _token_error("invalid_request", "code and code_verifier required")
            row = (
                await db.execute(
                    select(OAuthAuthorizationCode).where(
                        OAuthAuthorizationCode.code_hash == hash_token(code)
                    )
                )
            ).scalar_one_or_none()
            if row is None or not row.is_redeemable or row.client_id != client.client_id:
                return await _invalid_grant(request, limiter, settings)
            if redirect_uri != row.redirect_uri:
                return await _invalid_grant(request, limiter, settings, "redirect_uri mismatch")
            if not _verify_pkce(code_verifier, row.code_challenge):
                return await _invalid_grant(request, limiter, settings, "PKCE verification failed")
            row.used = True  # single-use (OAS-3)
            db.add(row)
            access, refresh, token_row = _issue_pair(
                client.client_id, row.user_id, row.endpoint_id, row.scope
            )
            db.add(token_row)
            await db.commit()
            return _token_response(access, refresh, row.scope)

        if grant_type == "refresh_token":
            if not refresh_token:
                return _token_error("invalid_request", "refresh_token required")
            row = (
                await db.execute(
                    select(OAuthAccessToken).where(
                        OAuthAccessToken.refresh_token_hash == hash_token(refresh_token)
                    )
                )
            ).scalar_one_or_none()
            if row is None or not row.is_refreshable or row.client_id != client.client_id:
                return await _invalid_grant(request, limiter, settings)
            row.revoked = True  # rotation (OAS-4)
            db.add(row)
            access, refresh, token_row = _issue_pair(
                client.client_id, row.user_id, row.endpoint_id, row.scope
            )
            db.add(token_row)
            await db.commit()
            return _token_response(access, refresh, row.scope)

    return _token_error("unsupported_grant_type")


def _basic_password(authorization: str | None) -> str | None:
    """Extract the password from an HTTP Basic header (RFC 7662 client auth)."""
    if not authorization or not authorization.lower().startswith("basic "):
        return None
    import base64
    import binascii

    try:
        decoded = base64.b64decode(authorization[6:], validate=True).decode()
    except (binascii.Error, UnicodeDecodeError):
        return None
    _, _, password = decoded.partition(":")
    return password or None


@router.post("/oauth/introspect", include_in_schema=False)
async def introspect(
    request: Request,
    session_factory: SessionFactoryProvider,
    settings: SettingsProvider,
    token: str = Form(...),
):
    """Requires a service API key; reports sub + endpoint audience.

    Upstream resource servers doing RFC 7662 client auth (HTTP Basic) may
    supply the service key as the client secret — the sequence application-layer's
    servers use against their gateway (OAS-5 "client credentials").
    """
    async with session_factory() as db:
        auth_service = AuthService(db)
        caller = await auth_service.authenticate_api_key(
            authorization=request.headers.get("authorization"),
            x_api_key=request.headers.get("x-api-key"),
        )
        if caller is None:
            caller = await auth_service.resolve_api_key(
                _basic_password(request.headers.get("authorization"))
            )
        if caller is None or caller.kind != ApiKeyKind.SERVICE:
            raise HTTPException(401, "service API key required")

        row = (
            await db.execute(
                select(OAuthAccessToken).where(
                    OAuthAccessToken.access_token_hash == hash_token(token)
                )
            )
        ).scalar_one_or_none()
        if row is None:
            # FWD-4: forwarded bearers may be gateway API keys, not OAuth
            # tokens — report them with the FWD-3 identity format so
            # introspecting upstreams can serve api_key callers too.
            key = await auth_service.resolve_api_key(token)
            if key is not None:
                return {
                    "active": True,
                    "sub": f"api_key:{key.id}",
                    "token_use": "api_key",
                }
            return {"active": False}
        if not row.is_usable:
            return {"active": False}
        user = (await db.execute(select(User).where(User.id == row.user_id))).scalar_one_or_none()
        endpoint = (
            await db.execute(select(Endpoint).where(Endpoint.id == row.endpoint_id))
        ).scalar_one_or_none()
    if user is None or not user.is_active:
        return {"active": False}
    return {
        "active": True,
        "sub": str(row.user_id),
        "client_id": row.client_id,
        "scope": row.scope,
        "exp": int(row.expires_at.timestamp()),
        "aud": endpoint_resource(settings, endpoint.name) if endpoint else None,
        "email": user.email,
    }


@router.post("/oauth/revoke", include_in_schema=False)
async def revoke(session_factory: SessionFactoryProvider, token: str = Form(...)):
    """RFC 7009: revokes by access or refresh token; always 200."""
    h = hash_token(token)
    async with session_factory() as db:
        row = (
            await db.execute(
                select(OAuthAccessToken).where(
                    (OAuthAccessToken.access_token_hash == h)
                    | (OAuthAccessToken.refresh_token_hash == h)
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            row.revoked = True
            db.add(row)
            await db.commit()
    return {"revoked": True}


async def purge_expired(session_factory) -> int:
    """Delete expired codes/tokens and stale never-used clients."""
    from sqlalchemy import delete

    now = utcnow()
    async with session_factory() as db:
        removed = 0
        result = await db.execute(
            delete(OAuthAuthorizationCode).where(OAuthAuthorizationCode.expires_at < now)
        )
        removed += result.rowcount or 0
        result = await db.execute(
            delete(OAuthAccessToken).where(
                OAuthAccessToken.refresh_expires_at < now - timedelta(days=1)
            )
        )
        removed += result.rowcount or 0
        result = await db.execute(
            delete(OAuthClient).where(
                OAuthClient.last_used_at.is_(None),  # type: ignore[union-attr]
                OAuthClient.created_at < now - timedelta(days=7),
            )
        )
        removed += result.rowcount or 0
        await db.commit()
        return removed


PURGE_INTERVAL_SECONDS = 600


async def purge_expired_forever(session_factory) -> None:
    """Run purge_expired on a fixed interval for the life of the process.

    One failed sweep never ends the loop: the next interval retries.
    """
    while True:
        await asyncio.sleep(PURGE_INTERVAL_SECONDS)
        try:
            removed = await purge_expired(session_factory)
            if removed:
                log.info("oauth.purged", removed=removed)
        except Exception:
            log.warning("oauth.purge_failed", exc_info=True)
