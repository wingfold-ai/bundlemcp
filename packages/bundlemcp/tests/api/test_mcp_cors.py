"""Browser origins per endpoint: CORS and the Origin check on MCP routes (EP-24, SEC-5, SEC-4)."""

import pytest

from tests.api.test_oidc import FakeOidcProvider
from tests.api.test_web_origins import PUBLIC_URL, WEB_ORIGIN, _login
from tests.conftest import SERVICE_KEY, hermetic_settings, seed_api_key, serving

APP = "https://app.example"
EVIL = "https://evil.example"
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-11-25", "capabilities": {}},
}
PREFLIGHT = {
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "authorization, content-type, mcp-protocol-version",
}


@pytest.fixture
async def env(engine, redis):
    """The gateway with an admin UI origin configured, signed in as its admin."""
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
        await _login(http, provider)
        await http.put("/api/v1/bundles/b1", json={"name": "b1"}, headers={"Origin": WEB_ORIGIN})
        yield http


async def _endpoint(http, name: str, auth_modes: list[str], allowed: list[str] | None) -> dict:
    body: dict = {"name": name, "bundle_name": "b1", "auth_modes": auth_modes}
    if auth_modes == ["none"]:
        body["allow_unauthenticated"] = True
    if allowed is not None:
        body["allowed_origins"] = allowed
    resp = await http.put(f"/api/v1/endpoints/{name}", json=body, headers={"Origin": WEB_ORIGIN})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _endpoint_key(http) -> str:
    created = await http.post(
        "/api/v1/api-keys", json={"name": "k", "kind": "endpoint"}, headers={"Origin": WEB_ORIGIN}
    )
    return created.json()["key"]


def _granted(resp) -> str | None:
    return resp.headers.get("access-control-allow-origin")


async def test_ep24_listed_origin_is_served_with_cors(env):
    """EP-24/SEC-5: a listed origin is served, and can read the session id."""
    await _endpoint(env, "main", ["api_key"], [APP])
    key = await _endpoint_key(env)
    env.cookies.clear()
    headers = {"Origin": APP, "Authorization": f"Bearer {key}"}
    resp = await env.post("/main/mcp", json=INITIALIZE, headers=headers)
    assert resp.status_code == 200
    assert _granted(resp) == APP
    assert "access-control-allow-credentials" not in resp.headers
    exposed = resp.headers["access-control-expose-headers"].lower()
    assert "mcp-session-id" in exposed and "www-authenticate" in exposed
    assert "origin" in resp.headers["vary"].lower()
    session = resp.headers["mcp-session-id"]
    closed = await env.delete("/main/mcp", headers={**headers, "Mcp-Session-Id": session})
    assert _granted(closed) == APP


async def test_sec5_unauthenticated_challenge_is_readable(env):
    """SEC-5: a browser on an allowed origin can read the 401 and its WWW-Authenticate."""
    await _endpoint(env, "main", ["oauth"], None)  # the default for oauth is any origin
    env.cookies.clear()
    resp = await env.post("/main/mcp", json=INITIALIZE, headers={"Origin": APP})
    assert resp.status_code == 401
    assert _granted(resp) == APP
    assert "www-authenticate" in resp.headers


async def test_ep24_other_origin_is_refused_before_authentication(env):
    """EP-24: an origin off the list gets 403 with no grant; the credential is never checked."""
    await _endpoint(env, "main", ["api_key"], [APP])
    env.cookies.clear()
    resp = await env.post(
        "/main/mcp",
        json=INITIALIZE,
        headers={"Origin": EVIL, "Authorization": "Bearer not-a-real-key"},
    )
    assert resp.status_code == 403  # an invalid key would have been a 401
    assert resp.json()["error"]["code"] == -32600
    assert _granted(resp) is None


async def test_ep24_open_endpoint_refuses_cross_site_browsers_by_default(env):
    """EP-24: an endpoint created open and without a list allows no other site."""
    created = await _endpoint(env, "open", ["none"], None)
    assert created["allowed_origins"] == []
    env.cookies.clear()
    resp = await env.post("/open/mcp", json=INITIALIZE, headers={"Origin": EVIL})
    assert resp.status_code == 403
    served = await env.post("/open/mcp", json=INITIALIZE)  # no Origin: not a browser
    assert served.status_code == 200


async def test_ep24_clients_without_an_origin_and_the_gateways_own_origin_pass(env):
    """EP-24: no Origin is unaffected by an empty list; the gateway's own origin always passes."""
    await _endpoint(env, "main", ["api_key"], [])
    key = await _endpoint_key(env)
    env.cookies.clear()
    auth = {"Authorization": f"Bearer {key}"}
    assert (await env.post("/main/mcp", json=INITIALIZE, headers=auth)).status_code == 200
    own = await env.post("/main/mcp", json=INITIALIZE, headers={**auth, "Origin": PUBLIC_URL})
    assert own.status_code == 200
    assert _granted(own) == PUBLIC_URL


async def test_sec5_preflight_is_answered(env):
    """SEC-5: a preflight from an allowed origin gets the methods, headers and a max age."""
    await _endpoint(env, "main", ["oauth"], [APP])
    env.cookies.clear()
    resp = await env.options("/main/mcp", headers={"Origin": APP, **PREFLIGHT})
    assert resp.status_code == 204
    assert _granted(resp) == APP
    assert "POST" in resp.headers["access-control-allow-methods"]
    allowed = resp.headers["access-control-allow-headers"].lower()
    assert all(h in allowed for h in ("authorization", "content-type", "mcp-protocol-version"))
    assert resp.headers["access-control-max-age"] == "600"
    assert "access-control-allow-credentials" not in resp.headers


async def test_sec5_preflight_from_an_origin_the_endpoint_does_not_allow(env):
    """SEC-5: a refused preflight gets 403 and no Access-Control-Allow-* header at all."""
    await _endpoint(env, "main", ["oauth"], [APP])
    env.cookies.clear()
    resp = await env.options("/main/mcp", headers={"Origin": EVIL, **PREFLIGHT})
    assert resp.status_code == 403
    assert not [h for h in resp.headers if h.lower().startswith("access-control-allow")]


async def test_sec5_an_admin_session_cookie_never_authenticates_an_mcp_request(env):
    """SEC-5: the MCP endpoint ignores the admin UI's session cookie; only headers authenticate."""
    await _endpoint(env, "main", ["oauth"], None)
    assert env.cookies  # the admin session is held
    resp = await env.post("/main/mcp", json=INITIALIZE, headers={"Origin": APP})
    assert resp.status_code == 401


async def test_sec4_management_api_stays_allow_listed(env):
    """SEC-4/SEC-5: an origin outside BUNDLEMCP_WEB_ORIGINS gets no CORS grant on /api/v1."""
    resp = await env.get("/api/v1/upstreams", headers={"Origin": APP})
    assert _granted(resp) is None
    listed = await env.get("/api/v1/upstreams", headers={"Origin": WEB_ORIGIN})
    assert _granted(listed) == WEB_ORIGIN


async def test_sec5_mcp_cors_needs_no_web_origins(engine, redis):
    """SEC-5: without BUNDLEMCP_WEB_ORIGINS the MCP route still answers CORS; the API does not."""
    await seed_api_key(engine, SERVICE_KEY)
    async with serving(engine, redis, settings=hermetic_settings(), bearer=SERVICE_KEY) as (
        http,
        _app,
    ):
        await http.put("/api/v1/bundles/b1", json={"name": "b1"})
        await http.put(
            "/api/v1/endpoints/main",
            json={"name": "main", "bundle_name": "b1", "auth_modes": ["oauth"]},
        )
        mcp = await http.post(
            "/main/mcp", json=INITIALIZE, headers={"Origin": APP, "Authorization": ""}
        )
        api = await http.get("/api/v1/upstreams", headers={"Origin": APP})
    assert mcp.status_code == 401 and _granted(mcp) == APP
    assert _granted(api) is None
