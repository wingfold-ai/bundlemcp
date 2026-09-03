"""OAuth 2.1 server tests (spec 20: OAS-1..11, EP-3a/3b) — full PKCE flow.

The OIDC login itself is exercised in test_oidc.py; here a browser session is
seeded directly so the authorize/consent/token machinery is tested hermetically.
"""

import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlparse

import pytest
from bundlemcp.api.app import create_app
from bundlemcp.api.composition_overrides import CompositionOverrides
from bundlemcp.crypto import API_KEY_PREFIX, display_prefix, generate_token, hash_token
from bundlemcp.models import (
    ApiKey,
    ApiKeyKind,
    Bundle,
    Endpoint,
    OAuthAccessToken,
    User,
)
from bundlemcp.oauth.session_cookie import SESSION_COOKIE
from bundlemcp.settings import Settings
from bundlemcp.store import session_factory
from bundlemcp.store.admin_sessions import AdminSession
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select

SERVICE_KEY = generate_token(API_KEY_PREFIX)
PUBLIC_URL = "http://gw"


def make_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    return verifier, challenge


@pytest.fixture
async def oauth_env(engine: AsyncEngine, redis: FakeRedis):
    settings = Settings(_env_file=None, database_url="sqlite+aiosqlite://", public_url=PUBLIC_URL)
    app = create_app(settings, overrides=CompositionOverrides(engine=engine, redis=redis))

    factory = session_factory(engine)
    async with factory() as db:
        user = User(oidc_issuer="http://idp", oidc_sub="alice", email="alice@example.com")
        bundle = Bundle(name="b")
        db.add_all([user, bundle])
        await db.commit()
        await db.refresh(user)
        await db.refresh(bundle)
        ep1 = Endpoint(name="ep1", bundle_id=bundle.id, auth_modes=["oauth"], profile="claude")
        ep2 = Endpoint(name="ep2", bundle_id=bundle.id, auth_modes=["oauth"], profile="claude")
        db.add_all(
            [
                ep1,
                ep2,
                ApiKey(
                    name="svc",
                    key_hash=hash_token(SERVICE_KEY),
                    key_prefix=display_prefix(SERVICE_KEY),
                    kind=ApiKeyKind.SERVICE,
                ),
            ]
        )
        await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=PUBLIC_URL, follow_redirects=False
    ) as http:
        async with app.router.lifespan_context(app):
            # seed a browser session for the user (login flow tested separately)
            session_id = await app.state.container.admin_sessions.create(
                AdminSession(user_id=str(user.id), email=user.email, is_admin=False)
            )
            http.cookies.set(SESSION_COOKIE, session_id)
            yield http, app, user


async def _register_client(http) -> str:
    resp = await http.post(
        "/oauth/register",
        json={"redirect_uris": ["https://client.example/cb"], "client_name": "TestClient"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "client_secret" not in body  # public client by default (OAS-2)
    return body["client_id"]


async def _authorize(http, client_id, challenge, resource, expect_consent=True) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": "https://client.example/cb",
        "response_type": "code",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": "st4te",
        "resource": resource,
    }
    resp = await http.get("/oauth/authorize", params=params)
    if expect_consent:
        assert resp.status_code == 200  # consent page (OAS-11)
        assert "Authorize access" in resp.text
        token = resp.text.split('name="token" value="')[1].split('"')[0]
        resp = await http.post("/oauth/consent", data={"token": token, "action": "approve"})
    assert resp.status_code == 302, resp.text
    location = urlparse(resp.headers["location"])
    query = parse_qs(location.query)
    assert query["state"] == ["st4te"]
    return query["code"][0]


async def _exchange(http, client_id, code, verifier) -> dict:
    resp = await http.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://client.example/cb",
            "code_verifier": verifier,
            "client_id": client_id,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_discovery_metadata(oauth_env):
    """OAS-1: AS metadata + per-endpoint protected-resource metadata."""
    http, app, user = oauth_env
    meta = (await http.get("/.well-known/oauth-authorization-server")).json()
    assert meta["issuer"] == PUBLIC_URL
    assert meta["code_challenge_methods_supported"] == ["S256"]

    prm = (await http.get("/.well-known/oauth-protected-resource/ep1/mcp")).json()
    assert prm["resource"] == f"{PUBLIC_URL}/ep1/mcp"
    assert prm["authorization_servers"] == [PUBLIC_URL]


async def test_full_pkce_flow_and_mcp_call(oauth_env):
    """OAS-2/3/4/10/11 + EP-3a happy path down to an authenticated initialize."""
    http, app, user = oauth_env
    client_id = await _register_client(http)
    verifier, challenge = make_pkce()

    code = await _authorize(http, client_id, challenge, f"{PUBLIC_URL}/ep1/mcp")
    tokens = await _exchange(http, client_id, code, verifier)
    assert tokens["access_token"].startswith("bmcp_at_")
    assert tokens["token_type"] == "Bearer"

    # the bearer works on the endpoint it was issued for
    resp = await http.post(
        "/ep1/mcp",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25", "capabilities": {}},
        },
    )
    assert resp.status_code == 200, resp.text
    assert "mcp-session-id" in resp.headers


async def test_consent_skipped_on_second_authorize(oauth_env):
    """OAS-11: persistent consent."""
    http, app, user = oauth_env
    client_id = await _register_client(http)
    verifier, challenge = make_pkce()
    await _authorize(http, client_id, challenge, f"{PUBLIC_URL}/ep1/mcp")

    verifier2, challenge2 = make_pkce()
    code = await _authorize(
        http, client_id, challenge2, f"{PUBLIC_URL}/ep1/mcp", expect_consent=False
    )
    assert code


async def test_token_bound_to_endpoint_audience(oauth_env):
    """EP-3a/OAS-10: a token for ep1 is rejected at ep2 with the 401 challenge."""
    http, app, user = oauth_env
    client_id = await _register_client(http)
    verifier, challenge = make_pkce()
    code = await _authorize(http, client_id, challenge, f"{PUBLIC_URL}/ep1/mcp")
    tokens = await _exchange(http, client_id, code, verifier)

    resp = await http.post(
        "/ep2/mcp",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert resp.status_code == 401
    assert "resource_metadata" in resp.headers["WWW-Authenticate"]


async def test_code_single_use_and_pkce_verified(oauth_env):
    """OAS-3: bad verifier rejected; code burns on first use."""
    http, app, user = oauth_env
    client_id = await _register_client(http)
    verifier, challenge = make_pkce()
    code = await _authorize(http, client_id, challenge, f"{PUBLIC_URL}/ep1/mcp")

    bad = await http.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://client.example/cb",
            "code_verifier": "wrong-verifier-wrong-verifier-wrong-verifier",
            "client_id": client_id,
        },
    )
    assert bad.status_code == 400
    assert bad.json()["error"] == "invalid_grant"

    # code was consumed by the failed attempt? No — only on success it's marked
    # used before verification fails? Ensure a correct retry still works or is
    # rejected consistently:
    retry = await http.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://client.example/cb",
            "code_verifier": verifier,
            "client_id": client_id,
        },
    )
    assert retry.status_code == 200  # failed PKCE attempt does not burn the code

    replay = await http.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://client.example/cb",
            "code_verifier": verifier,
            "client_id": client_id,
        },
    )
    assert replay.status_code == 400  # single-use after success


async def test_refresh_rotation_revokes_old(oauth_env):
    """OAS-4: refresh rotates; the old refresh token stops working."""
    http, app, user = oauth_env
    client_id = await _register_client(http)
    verifier, challenge = make_pkce()
    code = await _authorize(http, client_id, challenge, f"{PUBLIC_URL}/ep1/mcp")
    tokens = await _exchange(http, client_id, code, verifier)

    refreshed = await http.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": client_id,
        },
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] != tokens["access_token"]

    replay = await http.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": client_id,
        },
    )
    assert replay.status_code == 400  # rotated away

    # old access token row is revoked
    async with app.state.container.session_factory() as db:
        rows = (await db.execute(select(OAuthAccessToken))).scalars().all()
    assert any(r.revoked for r in rows)


async def test_introspection_requires_service_key(oauth_env):
    """OAS-5/UPO-7."""
    http, app, user = oauth_env
    client_id = await _register_client(http)
    verifier, challenge = make_pkce()
    code = await _authorize(http, client_id, challenge, f"{PUBLIC_URL}/ep1/mcp")
    tokens = await _exchange(http, client_id, code, verifier)

    anon = await http.post("/oauth/introspect", data={"token": tokens["access_token"]})
    assert anon.status_code == 401

    resp = await http.post(
        "/oauth/introspect",
        data={"token": tokens["access_token"]},
        headers={"Authorization": f"Bearer {SERVICE_KEY}"},
    )
    body = resp.json()
    assert body["active"] is True
    assert body["sub"] == str(user.id)
    assert body["aud"] == f"{PUBLIC_URL}/ep1/mcp"
    assert body["email"] == "alice@example.com"

    # RFC 7662 client auth (OAS-5 "client credentials"): the service key may
    # arrive as the HTTP Basic client secret — what application-layer's upstreams send.
    import base64

    basic = base64.b64encode(f"any-client:{SERVICE_KEY}".encode()).decode()
    via_basic = await http.post(
        "/oauth/introspect",
        data={"token": tokens["access_token"]},
        headers={"Authorization": f"Basic {basic}"},
    )
    assert via_basic.json()["active"] is True

    wrong_basic = base64.b64encode(b"any-client:not-a-key").decode()
    denied = await http.post(
        "/oauth/introspect",
        data={"token": tokens["access_token"]},
        headers={"Authorization": f"Basic {wrong_basic}"},
    )
    assert denied.status_code == 401

    # gateway API keys introspect as active with the FWD-3 identity format,
    # so introspecting upstreams can serve api_key callers (FWD-4)
    key_introspect = await http.post(
        "/oauth/introspect",
        data={"token": SERVICE_KEY},
        headers={"Authorization": f"Bearer {SERVICE_KEY}"},
    )
    body = key_introspect.json()
    assert body["active"] is True
    assert body["sub"].startswith("api_key:")

    unknown = await http.post(
        "/oauth/introspect",
        data={"token": "bmcp_sk_doesnotexist"},
        headers={"Authorization": f"Bearer {SERVICE_KEY}"},
    )
    assert unknown.json() == {"active": False}


async def test_revocation(oauth_env):
    """OAS-6."""
    http, app, user = oauth_env
    client_id = await _register_client(http)
    verifier, challenge = make_pkce()
    code = await _authorize(http, client_id, challenge, f"{PUBLIC_URL}/ep1/mcp")
    tokens = await _exchange(http, client_id, code, verifier)

    await http.post("/oauth/revoke", data={"token": tokens["access_token"]})
    resp = await http.post(
        "/ep1/mcp",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert resp.status_code == 401


async def test_authorize_requires_login_redirect(oauth_env):
    """OAS-3: no browser session -> redirect into /login with next."""
    http, app, user = oauth_env
    client_id = await _register_client(http)
    _, challenge = make_pkce()
    http.cookies.delete(SESSION_COOKIE)
    resp = await http.get(
        "/oauth/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": "https://client.example/cb",
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": f"{PUBLIC_URL}/ep1/mcp",
        },
    )
    assert resp.status_code == 302
    assert resp.headers["location"].startswith("/login?next=")


async def test_authorize_login_next_uses_public_url_behind_proxy(oauth_env):
    """DEP-1: behind a proxy the login return URL is built from public_url, not
    the internal Host, so the post-login next-clamp preserves it (not '/')."""
    from urllib.parse import parse_qs, unquote, urlparse

    http, app, user = oauth_env
    client_id = await _register_client(http)
    _, challenge = make_pkce()
    http.cookies.delete(SESSION_COOKIE)
    # simulate cloudflared: the app is reached on an internal host header
    resp = await http.get(
        "/oauth/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": "https://client.example/cb",
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": f"{PUBLIC_URL}/ep1/mcp",
        },
        headers={"host": "localhost:8000"},
    )
    assert resp.status_code == 302
    next_url = unquote(parse_qs(urlparse(resp.headers["location"]).query)["next"][0])
    # the return URL must be the public origin, not the internal host
    assert next_url.startswith(PUBLIC_URL + "/oauth/authorize")
    assert "localhost:8000" not in next_url


async def test_missing_resource_rejected(oauth_env):
    """OAS-10: resource is required and must be a bundlemcp endpoint."""
    http, app, user = oauth_env
    client_id = await _register_client(http)
    _, challenge = make_pkce()
    resp = await http.get(
        "/oauth/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": "https://client.example/cb",
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
    )
    assert resp.status_code == 302
    assert "error=invalid_target" in resp.headers["location"]
