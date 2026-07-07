"""Authorization endpoint + consent screen."""

import json
import secrets
import uuid
from datetime import timedelta
from urllib.parse import quote, urlencode

import structlog
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, PackageLoader, select_autoescape
from sqlmodel import select

from bundlemcp.models import (
    Bundle,
    Endpoint,
    OAuthAuthorizationCode,
    OAuthClient,
    OAuthConsent,
    User,
    utcnow,
)
from bundlemcp.oauth.adminsessions import SESSION_COOKIE
from bundlemcp.oauth.urls import endpoint_name_from_resource, issuer
from bundlemcp.security import hash_token

log = structlog.get_logger(__name__)

router = APIRouter(tags=["oauth"])

CODE_TTL = timedelta(minutes=10)  # OAS-3
PENDING_CONSENT_KEY = "bmcp:pendingconsent:{token}"
PENDING_CONSENT_TTL = 600

_jinja = Environment(
    loader=PackageLoader("bundlemcp.oauth", "templates"),
    autoescape=select_autoescape(["html"]),
)

# SEC-6 hardening for browser-facing auth pages
PAGE_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
}


async def current_session_user(request: Request) -> User | None:
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        return None
    session = await request.app.state.admin_sessions.load(session_id)
    if session is None:
        return None
    async with request.app.state.session_factory() as db:
        user = (
            await db.execute(select(User).where(User.id == uuid.UUID(session.user_id)))
        ).scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    return user


def _redirect_error(redirect_uri: str, state: str | None, error: str, description: str = ""):
    params = {"error": error}
    if description:
        params["error_description"] = description
    if state:
        params["state"] = state
    return RedirectResponse(f"{redirect_uri}?{urlencode(params)}", status_code=302)


async def _issue_code(request: Request, pending: dict) -> RedirectResponse:
    raw_code = secrets.token_urlsafe(32)
    code = OAuthAuthorizationCode(
        code_hash=hash_token(raw_code),
        client_id=pending["client_id"],
        user_id=uuid.UUID(pending["user_id"]),
        endpoint_id=uuid.UUID(pending["endpoint_id"]),
        redirect_uri=pending["redirect_uri"],
        scope=pending["scope"],
        code_challenge=pending["code_challenge"],
        code_challenge_method="S256",
        expires_at=utcnow() + CODE_TTL,
    )
    async with request.app.state.session_factory() as db:
        db.add(code)
        await db.commit()
    params = {"code": raw_code}
    if pending.get("state"):
        params["state"] = pending["state"]
    return RedirectResponse(f"{pending['redirect_uri']}?{urlencode(params)}", status_code=302)


@router.get("/oauth/authorize", include_in_schema=False)
async def authorize(request: Request):  # noqa: PLR0911 - protocol branching
    q = request.query_params
    client_id = q.get("client_id", "")
    redirect_uri = q.get("redirect_uri", "")
    state = q.get("state")

    async with request.app.state.session_factory() as db:
        client = (
            await db.execute(select(OAuthClient).where(OAuthClient.client_id == client_id))
        ).scalar_one_or_none()
    if client is None:
        raise HTTPException(400, "unknown client")  # never redirect on client errors
    if redirect_uri not in client.redirect_uris:
        raise HTTPException(400, "redirect_uri not registered")

    if q.get("response_type") != "code":
        return _redirect_error(redirect_uri, state, "unsupported_response_type")
    code_challenge = q.get("code_challenge", "")
    if not code_challenge or q.get("code_challenge_method", "S256") != "S256":
        return _redirect_error(
            redirect_uri, state, "invalid_request", "PKCE S256 code_challenge required"
        )

    # OAS-10: resolve the endpoint audience from `resource`
    settings = request.app.state.settings
    resource = q.get("resource", "")
    endpoint_name = endpoint_name_from_resource(settings, resource) if resource else None
    if endpoint_name is None:
        return _redirect_error(
            redirect_uri, state, "invalid_target", "resource must identify a bundlemcp endpoint"
        )
    async with request.app.state.session_factory() as db:
        endpoint = (
            await db.execute(select(Endpoint).where(Endpoint.name == endpoint_name))
        ).scalar_one_or_none()
        if endpoint is None or not endpoint.enabled or "oauth" not in endpoint.auth_modes:
            return _redirect_error(redirect_uri, state, "invalid_target", "unknown endpoint")
        bundle = (
            await db.execute(select(Bundle).where(Bundle.id == endpoint.bundle_id))
        ).scalar_one()

    # OAS-3: needs an authenticated human — bounce through OIDC login.
    # Build the return URL from public_url (DEP-1), never the incoming Host —
    # behind a reverse proxy request.url is the internal origin, which the
    # browser can't return to and the login next-clamp would reject.
    user = await current_session_user(request)
    if user is None:
        base = issuer(request.app.state.settings)
        return_url = f"{base}{request.url.path}"
        if request.url.query:
            return_url += f"?{request.url.query}"
        return RedirectResponse(f"/login?next={quote(return_url, safe='')}", status_code=302)

    pending = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": q.get("scope") or client.scope,
        "code_challenge": code_challenge,
        "endpoint_id": str(endpoint.id),
        "user_id": str(user.id),
    }

    # OAS-11: persistent consent skips the screen
    async with request.app.state.session_factory() as db:
        consent = (
            await db.execute(
                select(OAuthConsent).where(
                    OAuthConsent.user_id == user.id,
                    OAuthConsent.client_id == client_id,
                    OAuthConsent.endpoint_id == endpoint.id,
                    OAuthConsent.revoked_at.is_(None),  # type: ignore[union-attr]
                )
            )
        ).scalar_one_or_none()
    if consent is not None:
        return await _issue_code(request, pending)

    token = secrets.token_urlsafe(32)  # single-use, unguessable => CSRF-safe form
    await request.app.state.redis.set(
        PENDING_CONSENT_KEY.format(token=token), json.dumps(pending), ex=PENDING_CONSENT_TTL
    )
    html = _jinja.get_template("consent.html").render(
        client_name=client.client_name or client.client_id,
        endpoint_name=endpoint.name,
        bundle_name=bundle.name,
        scope=pending["scope"],
        token=token,
        consent_action="/oauth/consent",
        user_email=user.email or str(user.id),
    )
    return HTMLResponse(html, headers=PAGE_HEADERS)


@router.post("/oauth/consent", include_in_schema=False)
async def consent(request: Request, token: str = Form(...), action: str = Form(...)):
    key = PENDING_CONSENT_KEY.format(token=token)
    raw = await request.app.state.redis.get(key)
    await request.app.state.redis.delete(key)  # single-use
    if raw is None:
        raise HTTPException(400, "consent request expired")
    pending = json.loads(raw)

    user = await current_session_user(request)
    if user is None or str(user.id) != pending["user_id"]:
        raise HTTPException(403, "session mismatch")

    if action != "approve":
        return _redirect_error(pending["redirect_uri"], pending.get("state"), "access_denied")

    async with request.app.state.session_factory() as db:
        db.add(
            OAuthConsent(
                user_id=user.id,
                client_id=pending["client_id"],
                endpoint_id=uuid.UUID(pending["endpoint_id"]),
            )
        )
        await db.commit()
    log.info("oauth.consent_granted", client_id=pending["client_id"])
    return await _issue_code(request, pending)
