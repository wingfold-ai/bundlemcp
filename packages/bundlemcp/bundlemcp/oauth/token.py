"""Token endpoint, introspection, revocation."""

import base64
import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlmodel import select

from bundlemcp.gateway.proxy import client_ip
from bundlemcp.models import (
    ApiKeyKind,
    Endpoint,
    OAuthAccessToken,
    OAuthAuthorizationCode,
    OAuthClient,
    User,
    utcnow,
)
from bundlemcp.oauth.urls import endpoint_resource
from bundlemcp.security import (
    ACCESS_TOKEN_PREFIX,
    REFRESH_TOKEN_PREFIX,
    generate_token,
    hash_token,
    tokens_equal,
)
from bundlemcp.services import AuthService

log = structlog.get_logger(__name__)

router = APIRouter(tags=["oauth"])

ACCESS_TOKEN_TTL = timedelta(hours=1)  # OAS-4 (runtime Config later)
REFRESH_TOKEN_TTL = timedelta(days=7)


def _aware(dt: datetime | None) -> datetime | None:
    """sqlite returns naive datetimes; treat them as UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _token_error(error: str, description: str = "", status: int = 400) -> JSONResponse:
    body = {"error": error}
    if description:
        body["error_description"] = description
    return JSONResponse(body, status_code=status, headers={"Cache-Control": "no-store"})


def _verify_pkce(verifier: str, challenge: str) -> bool:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == challenge


async def _note_token_auth_failure(request: Request) -> JSONResponse | None:
    """Count an OAuth-token credential failure per client IP.

    Returns a 429 (+ Retry-After) once the IP is locked out, else None so the
    caller returns its own invalid_client/invalid_grant. Fails open on Redis.
    """
    limiter = getattr(request.app.state, "auth_failure_limiter", None)
    if limiter is None:
        return None
    result = await limiter.record_failure(client_ip(request, request.app.state.settings))
    if result.allowed:
        return None
    resp = _token_error("too_many_requests", "too many authentication failures", status=429)
    resp.headers["Retry-After"] = str(result.retry_after)
    return resp


async def _invalid_grant(request: Request, description: str = "") -> JSONResponse:
    """A failed grant is a credential-scan signal → count it, maybe 429."""
    locked = await _note_token_auth_failure(request)
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
    grant_type: str = Form(...),
    code: str = Form(None),
    redirect_uri: str = Form(None),
    code_verifier: str = Form(None),
    refresh_token: str = Form(None),
    client_id: str = Form(None),
    client_secret: str = Form(None),
):
    async with request.app.state.session_factory() as db:
        client = await _authenticate_client(request, db, client_id or "", client_secret)
        if client is None:
            locked = await _note_token_auth_failure(request)  # RATE-5
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
            if (
                row is None
                or row.used
                or row.client_id != client.client_id
                or _aware(row.expires_at) < utcnow()
            ):
                return await _invalid_grant(request)
            if redirect_uri != row.redirect_uri:
                return await _invalid_grant(request, "redirect_uri mismatch")
            if not _verify_pkce(code_verifier, row.code_challenge):
                return await _invalid_grant(request, "PKCE verification failed")
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
            if (
                row is None
                or row.revoked
                or row.client_id != client.client_id
                or _aware(row.refresh_expires_at) < utcnow()
            ):
                return await _invalid_grant(request)
            row.revoked = True  # rotation (OAS-4)
            db.add(row)
            access, refresh, token_row = _issue_pair(
                client.client_id, row.user_id, row.endpoint_id, row.scope
            )
            db.add(token_row)
            await db.commit()
            return _token_response(access, refresh, row.scope)

    return _token_error("unsupported_grant_type")


@router.post("/oauth/introspect", include_in_schema=False)
async def introspect(request: Request, token: str = Form(...)):
    """Requires a service API key; reports sub + endpoint audience."""
    async with request.app.state.session_factory() as db:
        caller = await AuthService(db).authenticate_api_key(
            authorization=request.headers.get("authorization"),
            x_api_key=request.headers.get("x-api-key"),
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
        if row is None or row.revoked or _aware(row.expires_at) < utcnow():
            return {"active": False}
        user = (
            await db.execute(select(User).where(User.id == row.user_id))
        ).scalar_one_or_none()
        endpoint = (
            await db.execute(select(Endpoint).where(Endpoint.id == row.endpoint_id))
        ).scalar_one_or_none()
    if user is None or not user.is_active:
        return {"active": False}
    settings = request.app.state.settings
    return {
        "active": True,
        "sub": str(row.user_id),
        "client_id": row.client_id,
        "scope": row.scope,
        "exp": int(_aware(row.expires_at).timestamp()),
        "aud": endpoint_resource(settings, endpoint.name) if endpoint else None,
        "email": user.email,
    }


@router.post("/oauth/revoke", include_in_schema=False)
async def revoke(request: Request, token: str = Form(...)):
    """RFC 7009: revokes by access or refresh token; always 200."""
    h = hash_token(token)
    async with request.app.state.session_factory() as db:
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
