"""Web-app origin handling (SEC-4): CORS allowlist + CSRF allowance for web origins."""

from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlparse

import pytest
from bundlemcp.domain.access.oidc_claims import OidcClaims
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.api.test_oidc import FakeOidcProvider
from tests.conftest import hermetic_settings, serving

PUBLIC_URL = "http://gw"
WEB_ORIGIN = "http://web:3000"


@pytest.fixture
async def env(engine: AsyncEngine, redis: FakeRedis) -> AsyncIterator[tuple]:
    settings = hermetic_settings(
        public_url=PUBLIC_URL, admin_emails=["admin@example.com"], web_origins=[WEB_ORIGIN]
    )
    provider = FakeOidcProvider()
    async with serving(
        engine,
        redis,
        settings=settings,
        base_url=PUBLIC_URL,
        follow_redirects=False,
        oidc_provider=provider,
    ) as (http, _app):
        yield http, provider


async def _login(http, provider) -> None:
    provider.claims_by_code["fake-code"] = OidcClaims(
        issuer="http://idp", sub="a", email="admin@example.com"
    )
    resp = await http.get("/login", params={"next": "/"})
    q = parse_qs(urlparse(resp.headers["location"]).query)
    await http.get("/login/callback", params={"code": q["code"][0], "state": q["state"][0]})


async def test_web_origin_passes_csrf_check(env):
    """SEC-4: an allowlisted web origin may perform cookie-authenticated mutations."""
    http, provider = env
    await _login(http, provider)
    body = {"name": "s1", "url": "http://s1/mcp"}

    ok = await http.put("/api/v1/servers/s1", json=body, headers={"Origin": WEB_ORIGIN})
    assert ok.status_code == 200

    # non-allowlisted origins are still rejected
    bad = await http.put("/api/v1/servers/s1", json=body, headers={"Origin": "http://evil.example"})
    assert bad.status_code == 403


async def test_cors_preflight_for_web_origin(env):
    """SEC-4: CORS allowlist is exactly the configured web origin(s), with credentials."""
    http, _provider = env
    resp = await http.options(
        "/api/v1/servers",
        headers={
            "Origin": WEB_ORIGIN,
            "Access-Control-Request-Method": "PUT",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == WEB_ORIGIN
    assert resp.headers["access-control-allow-credentials"] == "true"

    denied = await http.options(
        "/api/v1/servers",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "PUT",
        },
    )
    assert "access-control-allow-origin" not in denied.headers


async def test_login_next_redirect_clamped(env):
    """The post-login redirect only follows relative paths or allowlisted origins."""
    http, provider = env
    provider.claims_by_code["fake-code"] = OidcClaims(
        issuer="http://idp", sub="a", email="admin@example.com"
    )

    async def final_redirect(next_value: str) -> str:
        resp = await http.get("/login", params={"next": next_value})
        q = parse_qs(urlparse(resp.headers["location"]).query)
        cb = await http.get(
            "/login/callback", params={"code": q["code"][0], "state": q["state"][0]}
        )
        return cb.headers["location"]

    assert await final_redirect(f"{WEB_ORIGIN}/servers") == f"{WEB_ORIGIN}/servers"
    assert await final_redirect("/bundles") == "/bundles"
    assert await final_redirect("http://evil.example/phish") == "/"
    assert await final_redirect("//evil.example") == "/"


async def test_me_reports_session_identity(env):
    """UI-2: /me answers for any signed-in session; anonymous gets 401."""
    http, provider = env
    anonymous = await http.get("/api/v1/me")
    assert anonymous.status_code == 401

    await _login(http, provider)
    me = await http.get("/api/v1/me")
    assert me.status_code == 200
    body = me.json()
    assert body["kind"] == "admin"
    assert body["email"] == "admin@example.com"
    assert body["is_admin"] is True


async def test_me_for_non_admin_session(env):
    """A signed-in non-admin still sees their identity (drives the no-access page)."""
    http, provider = env
    provider.claims_by_code["fake-code"] = OidcClaims(
        issuer="http://idp", sub="u2", email="user@example.com"
    )
    resp = await http.get("/login", params={"next": "/"})
    q = parse_qs(urlparse(resp.headers["location"]).query)
    await http.get("/login/callback", params={"code": q["code"][0], "state": q["state"][0]})

    me = await http.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["kind"] == "user"
    assert me.json()["is_admin"] is False

    # but the management API itself stays closed to non-admins
    denied = await http.get("/api/v1/servers")
    assert denied.status_code == 401


async def test_origin_must_match_exactly(env):
    """SEC-4: an origin that merely starts with an allowed one is not allowed."""
    http, provider = env
    await _login(http, provider)
    body = {"name": "s1", "url": "http://s1/mcp"}

    for origin in (f"{PUBLIC_URL}.evil.test", f"{WEB_ORIGIN}.evil.test", "http://gw:8080"):
        bad = await http.put("/api/v1/servers/s1", json=body, headers={"Origin": origin})
        assert bad.status_code == 403, origin
    ok = await http.put("/api/v1/servers/s1", json=body, headers={"Origin": PUBLIC_URL + "/"})
    assert ok.status_code == 200


async def test_referer_must_sit_under_an_allowed_origin(env):
    """SEC-4: a Referer is a URL: a path under an allowed origin passes, a lookalike host fails."""
    http, provider = env
    await _login(http, provider)
    body = {"name": "s1", "url": "http://s1/mcp"}

    ok = await http.put(
        "/api/v1/servers/s1", json=body, headers={"Referer": f"{WEB_ORIGIN}/servers/s1"}
    )
    assert ok.status_code == 200
    bad = await http.put(
        "/api/v1/servers/s1", json=body, headers={"Referer": f"{WEB_ORIGIN}.evil.test/servers"}
    )
    assert bad.status_code == 403
