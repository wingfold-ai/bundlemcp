"""OIDC relying-party login + admin session lifecycle.

The IdP interaction is behind OidcProvider so hermetic tests inject a fake
issuer instead of reaching a real Keycloak.
"""

import secrets
from typing import Protocol
from urllib.parse import urlencode

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlmodel import select

from bundlemcp.models import User
from bundlemcp.oauth.adminsessions import SESSION_COOKIE, AdminSession
from bundlemcp.settings import Settings

log = structlog.get_logger(__name__)

router = APIRouter(tags=["auth"])

OIDC_STATE_KEY = "bmcp:oidcstate:{state}"
OIDC_STATE_TTL = 600


class OidcClaims(BaseModel):
    issuer: str
    sub: str
    email: str | None = None
    name: str | None = None
    groups: list[str] = []


class OidcProvider(Protocol):
    def authorize_url(self, *, state: str, nonce: str, redirect_uri: str) -> str: ...

    async def exchange(self, *, code: str, redirect_uri: str, nonce: str) -> OidcClaims: ...


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


@router.get("/login", include_in_schema=False)
async def login(request: Request, next: str = "/"):
    provider: OidcProvider | None = getattr(request.app.state, "oidc_provider", None)
    if provider is None:
        raise HTTPException(503, "no OIDC provider configured")
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


class AuthlibOidcProvider:
    """Real IdP via authlib (used in deployment; compose ships Keycloak)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._metadata: dict | None = None

    async def _load_metadata(self) -> dict:
        if self._metadata is None:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.get(self._settings.oidc_discovery_url)
                resp.raise_for_status()
                self._metadata = resp.json()
        return self._metadata

    def authorize_url(self, *, state: str, nonce: str, redirect_uri: str) -> str:
        # discovery is async; deployment preloads metadata at startup. For the
        # authorize redirect we build from the known authorization endpoint.
        assert self._metadata is not None, "call preload() at startup"
        params = {
            "response_type": "code",
            "client_id": self._settings.oidc_client_id,
            "redirect_uri": redirect_uri,
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
        }
        return f"{self._metadata['authorization_endpoint']}?{urlencode(params)}"

    async def preload(self) -> None:
        await self._load_metadata()

    async def exchange(self, *, code: str, redirect_uri: str, nonce: str) -> OidcClaims:
        import httpx
        from authlib.jose import jwt

        meta = await self._load_metadata()
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                meta["token_endpoint"],
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": self._settings.oidc_client_id,
                    "client_secret": self._settings.oidc_client_secret,
                },
            )
            token_resp.raise_for_status()
            id_token = token_resp.json()["id_token"]
            jwks_resp = await client.get(meta["jwks_uri"])
            jwks_resp.raise_for_status()
        claims = jwt.decode(id_token, jwks_resp.json())
        claims.validate()
        if claims.get("nonce") != nonce:
            raise HTTPException(400, "nonce mismatch")
        return OidcClaims(
            issuer=claims["iss"],
            sub=claims["sub"],
            email=claims.get("email"),
            name=claims.get("name"),
            groups=claims.get("groups", []),
        )


def build_provider(settings: Settings) -> OidcProvider | None:
    if not settings.oidc_discovery_url:
        return None
    return AuthlibOidcProvider(settings)
