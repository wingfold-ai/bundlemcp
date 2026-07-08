import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlmodel import select

from bundlemcp.models import User
from bundlemcp.oauth.adminsessions import SESSION_COOKIE, AdminSession
from bundlemcp.oauth.oidc._common import OIDC_STATE_KEY, OIDC_STATE_TTL, log
from bundlemcp.oauth.oidc.authlib_oidc_provider import AuthlibOidcProvider
from bundlemcp.oauth.oidc.oidc_claims import OidcClaims
from bundlemcp.oauth.oidc.oidc_provider import OidcProvider
from bundlemcp.settings import Settings

router = APIRouter(tags=["auth"])


def is_admin(claims: OidcClaims, settings: Settings) -> bool:
    """Admin status is re-evaluated on every login."""
    if claims.email and claims.email in settings.admin_emails:
        return True
    return "bundlemcp-admin" in claims.groups


async def provision_user(session_factory, claims: OidcClaims, settings: Settings) -> User:
    """Create-or-update by (issuer, sub); refresh is_admin on every login."""
    async with session_factory() as db:
        user = (
            await db.execute(
                select(User).where(
                    User.oidc_issuer == claims.issuer, User.oidc_sub == claims.sub
                )
            )
        ).scalar_one_or_none()
        if user is None:
            user = User(oidc_issuer=claims.issuer, oidc_sub=claims.sub)
        user.email = claims.email
        user.display_name = claims.name
        user.is_admin = is_admin(claims, settings)  # ADM-3
        if not user.is_active:
            user.is_active = True  # re-login reactivates unless admin-deactivated separately
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


def _redirect_uri(settings: Settings) -> str:
    return f"{str(settings.public_url).rstrip('/')}/login/callback"


def _safe_next(next_url: str, settings: Settings) -> str:
    """Clamp the post-login redirect to this app or an allowlisted web origin."""
    if next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    allowed = [str(settings.public_url).rstrip("/")] + [
        o.rstrip("/") for o in settings.web_origins
    ]
    if any(next_url == a or next_url.startswith(a + "/") for a in allowed):
        return next_url
    return "/"


@router.get("/login", include_in_schema=False)
async def login(request: Request, next: str = "/"):
    provider: OidcProvider | None = getattr(request.app.state, "oidc_provider", None)
    if provider is None:
        raise HTTPException(503, "no OIDC provider configured")
    next = _safe_next(next, request.app.state.settings)
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    await request.app.state.redis.set(
        OIDC_STATE_KEY.format(state=state),
        f"{nonce}\n{next}",
        ex=OIDC_STATE_TTL,
    )
    url = provider.authorize_url(
        state=state, nonce=nonce, redirect_uri=_redirect_uri(request.app.state.settings)
    )
    return RedirectResponse(url, status_code=302)


@router.get("/login/callback", include_in_schema=False)
async def login_callback(request: Request, code: str = "", state: str = ""):
    key = OIDC_STATE_KEY.format(state=state)
    stored = await request.app.state.redis.get(key)
    await request.app.state.redis.delete(key)  # single-use state (CSRF)
    if stored is None:
        raise HTTPException(400, "invalid or expired state")
    nonce, _, next_url = stored.partition("\n")

    provider: OidcProvider = request.app.state.oidc_provider
    settings = request.app.state.settings
    claims = await provider.exchange(
        code=code, redirect_uri=_redirect_uri(settings), nonce=nonce
    )
    user = await provision_user(request.app.state.session_factory, claims, settings)

    session_id = await request.app.state.admin_sessions.create(
        AdminSession(user_id=str(user.id), email=user.email, is_admin=user.is_admin)
    )
    secure = str(settings.public_url).startswith("https")
    response = RedirectResponse(next_url or "/", status_code=302)
    response.set_cookie(
        SESSION_COOKIE, session_id, **request.app.state.admin_sessions.cookie_kwargs(secure)
    )
    log.info("admin.login", user_id=str(user.id), is_admin=user.is_admin)
    return response


@router.post("/logout", include_in_schema=False)
async def logout(request: Request):
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        await request.app.state.admin_sessions.delete(session_id)  # ADM-5
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


def build_provider(settings: Settings) -> OidcProvider | None:
    if not settings.oidc_discovery_url:
        return None
    return AuthlibOidcProvider(settings)
