"""CORS chosen by path: permissive on MCP endpoints, allow-listed elsewhere (SEC-5, SEC-4)."""

import pytest

from tests.api.test_oidc import FakeOidcProvider
from tests.api.test_web_origins import PUBLIC_URL, WEB_ORIGIN, _login
from tests.conftest import hermetic_settings, serving

BROWSER_ORIGIN = "https://inspector.example"
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-11-25", "capabilities": {}},
}


@pytest.fixture
async def env(engine, redis):
    """The gateway with an admin UI origin configured, and its fake identity provider."""
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


async def _endpoint(http) -> None:
    """An OAuth-only endpoint, created by the signed-in admin."""
    origin = {"Origin": WEB_ORIGIN}
    await http.put("/api/v1/bundles/b1", json={"name": "b1"}, headers=origin)
    resp = await http.put(
        "/api/v1/endpoints/main",
        json={"name": "main", "bundle_name": "b1", "auth_modes": ["oauth"]},
        headers=origin,
    )
    assert resp.status_code == 200, resp.text


async def test_sec5_unauthenticated_challenge_is_readable_cross_origin(env):
    """SEC-5: a browser client on any origin can read the 401 and its WWW-Authenticate."""
    http, provider = env
    await _login(http, provider)
    await _endpoint(http)
    http.cookies.clear()
    resp = await http.post("/main/mcp", json=INITIALIZE, headers={"Origin": BROWSER_ORIGIN})
    assert resp.status_code == 401
    assert resp.headers["access-control-allow-origin"] == BROWSER_ORIGIN
    assert "access-control-allow-credentials" not in resp.headers
    exposed = {h.strip().lower() for h in resp.headers["access-control-expose-headers"].split(",")}
    assert {"mcp-session-id", "www-authenticate"} <= exposed
    assert "origin" in resp.headers["vary"].lower()


async def test_sec5_preflight_is_answered_without_authentication(env):
    """SEC-5: the preflight for the MCP transport's method and headers is allowed."""
    http, _ = env
    resp = await http.options(
        "/main/mcp",
        headers={
            "Origin": BROWSER_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization, content-type, mcp-protocol-version",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == BROWSER_ORIGIN
    assert "POST" in resp.headers["access-control-allow-methods"]
    allowed = resp.headers["access-control-allow-headers"].lower()
    assert all(h in allowed for h in ("authorization", "content-type", "mcp-protocol-version"))
    assert "access-control-allow-credentials" not in resp.headers


async def test_sec5_an_admin_session_cookie_never_authenticates_an_mcp_request(env):
    """SEC-5: the MCP endpoint ignores the admin UI's session cookie; only headers authenticate."""
    http, provider = env
    await _login(http, provider)
    await _endpoint(http)
    assert http.cookies  # the admin session is held
    resp = await http.post("/main/mcp", json=INITIALIZE, headers={"Origin": BROWSER_ORIGIN})
    assert resp.status_code == 401


async def test_sec4_management_api_stays_allow_listed(env):
    """SEC-4/SEC-5: an origin outside BUNDLEMCP_WEB_ORIGINS gets no CORS grant on /api/v1."""
    http, _ = env
    resp = await http.get("/api/v1/upstreams", headers={"Origin": BROWSER_ORIGIN})
    assert "access-control-allow-origin" not in resp.headers
    listed = await http.get("/api/v1/upstreams", headers={"Origin": WEB_ORIGIN})
    assert listed.headers["access-control-allow-origin"] == WEB_ORIGIN


@pytest.mark.parametrize("path", ["/main/mcp", "/api/v1/upstreams"])
async def test_sec5_mcp_cors_needs_no_web_origins(engine, redis, path):
    """SEC-5: without BUNDLEMCP_WEB_ORIGINS the MCP route still answers CORS; the API does not."""
    async with serving(engine, redis, settings=hermetic_settings()) as (http, _app):
        resp = await http.post(path, json=INITIALIZE, headers={"Origin": BROWSER_ORIGIN})
    granted = resp.headers.get("access-control-allow-origin")
    assert granted == (BROWSER_ORIGIN if path.endswith("/mcp") else None)
