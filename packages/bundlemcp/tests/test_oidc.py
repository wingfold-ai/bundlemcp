"""OIDC login + admin session + management-API session auth tests (spec 21).

A fake OidcProvider stands in for Keycloak (ARC-14) — the login/callback,
provisioning, admin re-eval, cookie session, and CSRF machinery are what we test.
"""

from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlparse

import pytest
from bundlemcp.api.app import create_app
from bundlemcp.api.composition_overrides import CompositionOverrides
from bundlemcp.models import User
from bundlemcp.oauth.oidc import OidcClaims
from bundlemcp.oauth.session_cookie import SESSION_COOKIE
from bundlemcp.settings import Settings
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select

PUBLIC_URL = "http://gw"


class FakeOidcProvider:
    """Deterministic stand-in: authorize_url points back at our callback, and
    exchange returns preset claims keyed by the code.
    """

    def __init__(self) -> None:
        self.claims_by_code: dict[str, OidcClaims] = {}
        self.last_state: str | None = None
        self.last_nonce: str | None = None

    def authorize_url(self, *, state, nonce, redirect_uri) -> str:
        self.last_state = state
        self.last_nonce = nonce
        return f"{redirect_uri}?code=fake-code&state={state}"

    async def exchange(self, *, code, redirect_uri, nonce) -> OidcClaims:
        return self.claims_by_code[code]


@pytest.fixture
async def env(engine: AsyncEngine, redis: FakeRedis) -> AsyncIterator[tuple]:
    settings = Settings(
        _env_file=None,
        database_url="sqlite+aiosqlite://",
        public_url=PUBLIC_URL,
        admin_emails=["admin@example.com"],
    )
    provider = FakeOidcProvider()
    app = create_app(
        settings, overrides=CompositionOverrides(engine=engine, redis=redis, oidc_provider=provider)
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=PUBLIC_URL, follow_redirects=False
    ) as http:
        async with app.router.lifespan_context(app):
            yield http, app, provider


async def _login(http, provider, claims: OidcClaims) -> None:
    provider.claims_by_code["fake-code"] = claims
    resp = await http.get("/login", params={"next": "/"})
    assert resp.status_code == 302
    location = resp.headers["location"]
    # our fake authorize_url redirects straight to the callback
    q = parse_qs(urlparse(location).query)
    callback = await http.get(
        "/login/callback", params={"code": q["code"][0], "state": q["state"][0]}
    )
    assert callback.status_code == 302, callback.text
    # httpx stores the Set-Cookie automatically


async def test_login_provisions_user_and_sets_admin(env):
    """ADM-2/ADM-3: first login provisions; admin email -> is_admin."""
    http, app, provider = env
    await _login(
        http,
        provider,
        OidcClaims(issuer="http://idp", sub="admin1", email="admin@example.com", name="Admin"),
    )
    async with app.state.container.session_factory() as db:
        user = (await db.execute(select(User))).scalar_one()
        assert user.email == "admin@example.com"
        assert user.is_admin is True
    assert http.cookies.get(SESSION_COOKIE)


async def test_admin_role_reevaluated_on_each_login(env):
    """ADM-3: dropping the admin email demotes on next login."""
    http, app, provider = env
    await _login(
        http, provider, OidcClaims(issuer="http://idp", sub="u1", email="admin@example.com")
    )
    async with app.state.container.session_factory() as db:
        assert (await db.execute(select(User))).scalar_one().is_admin is True

    # same subject logs in, but is no longer an admin email match
    await _login(
        http, provider, OidcClaims(issuer="http://idp", sub="u1", email="user@example.com")
    )
    async with app.state.container.session_factory() as db:
        users = (await db.execute(select(User))).scalars().all()
        assert len(users) == 1  # same (issuer, sub)
        assert users[0].is_admin is False


async def test_management_api_accepts_admin_session(env):
    """API-2: admin cookie session authorizes management calls."""
    http, app, provider = env
    await _login(
        http, provider, OidcClaims(issuer="http://idp", sub="a", email="admin@example.com")
    )
    resp = await http.get("/api/v1/servers")
    assert resp.status_code == 200


async def test_non_admin_session_rejected(env):
    """Non-admin users can't reach the management API."""
    http, app, provider = env
    await _login(http, provider, OidcClaims(issuer="http://idp", sub="b", email="user@example.com"))
    resp = await http.get("/api/v1/servers")
    assert resp.status_code == 401


async def test_csrf_origin_check_on_mutation(env):
    """SEC-4: cookie-authenticated mutations need a same-origin Origin/Referer."""
    http, app, provider = env
    await _login(
        http, provider, OidcClaims(issuer="http://idp", sub="a", email="admin@example.com")
    )
    body = {"name": "s1", "url": "http://s1/mcp"}

    # no Origin -> rejected
    bad = await http.put("/api/v1/servers/s1", json=body)
    assert bad.status_code == 403

    # cross-origin -> rejected
    cross = await http.put(
        "/api/v1/servers/s1", json=body, headers={"Origin": "http://evil.example"}
    )
    assert cross.status_code == 403

    # same-origin -> allowed
    ok = await http.put("/api/v1/servers/s1", json=body, headers={"Origin": PUBLIC_URL})
    assert ok.status_code == 200


async def test_logout_clears_session(env):
    http, app, provider = env
    await _login(
        http, provider, OidcClaims(issuer="http://idp", sub="a", email="admin@example.com")
    )
    await http.post("/logout", headers={"Origin": PUBLIC_URL})
    resp = await http.get("/api/v1/servers")
    assert resp.status_code == 401


async def test_deactivation_logs_out_and_revokes(env):
    """ADM-6: deactivating a user invalidates their admin session."""
    http, app, provider = env
    await _login(
        http, provider, OidcClaims(issuer="http://idp", sub="a", email="admin@example.com")
    )
    async with app.state.container.session_factory() as db:
        user = (await db.execute(select(User))).scalar_one()

    resp = await http.post(f"/api/v1/users/{user.id}:deactivate", headers={"Origin": PUBLIC_URL})
    assert resp.status_code == 200
    # session now fails is_active re-check
    follow = await http.get("/api/v1/servers")
    assert follow.status_code == 401
