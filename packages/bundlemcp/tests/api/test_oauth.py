"""OAuth 2.1 server tests (AUTH-1..11, EP-3a/3b) — full PKCE flow.

The OIDC login itself is exercised in test_oidc.py; here a browser session is
seeded directly so the authorize/consent/token machinery is tested hermetically.
"""

import base64
import hashlib
import secrets
import uuid
from urllib.parse import parse_qs, urlparse

import pytest
from bundlemcp.api.oauth.pages.page_headers import page_headers
from bundlemcp.api.oauth.session_cookie import SESSION_COOKIE
from bundlemcp.application.errors import InvalidInputError
from bundlemcp.application.oauth_server import ClientIdMetadataDocument
from bundlemcp.application.oauth_server.authorization_code_grant import AuthorizationCodeGrant
from bundlemcp.application.oauth_server.refresh_token_grant import RefreshTokenGrant
from bundlemcp.application.oauth_server.token_issuer import TokenIssuer
from bundlemcp.domain.oauth.oauth_error_code import OAuthErrorCode
from bundlemcp.domain.oauth.token_policy import TokenPolicy
from bundlemcp.domain.sessions.admin_session import AdminSession
from bundlemcp.domain.shared.clock import utcnow
from bundlemcp.domain.shared.secrets import hash_token
from bundlemcp.infrastructure.memory.manual_clock import ManualClock
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.bundle_row import BundleRow
from bundlemcp.infrastructure.postgres.rows.endpoint_row import EndpointRow
from bundlemcp.infrastructure.postgres.rows.oauth_access_token_row import OAuthAccessTokenRow
from bundlemcp.infrastructure.postgres.rows.user_row import UserRow
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select
from structlog.testing import capture_logs

from tests.conftest import SERVICE_KEY, hermetic_settings, seed_api_key, serving

PUBLIC_URL = "http://gw"
CIMD_CLIENT_ID = "https://client.example/oauth/client-metadata.json"


class FakeClientMetadataFetcher:
    """Serves one client's metadata document without touching the network (AUTH-13)."""

    def __init__(self) -> None:
        self.fetches = 0

    async def fetch(self, client_id_url: str) -> ClientIdMetadataDocument:
        self.fetches += 1
        if client_id_url != CIMD_CLIENT_ID:
            raise InvalidInputError("client metadata document could not be fetched")
        return ClientIdMetadataDocument(
            client_id=CIMD_CLIENT_ID,
            client_name="Metadata Client",
            redirect_uris=["https://client.example/cb"],
        )


def make_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    return verifier, challenge


@pytest.fixture
async def oauth_env(engine: AsyncEngine, redis: FakeRedis):
    await seed_api_key(engine, SERVICE_KEY)
    async with session_factory(engine)() as db:
        user = UserRow(oidc_issuer="http://idp", oidc_sub="alice", email="alice@example.com")
        bundle = BundleRow(name="b")
        db.add_all([user, bundle])
        await db.commit()
        await db.refresh(user)
        await db.refresh(bundle)
        ep1 = EndpointRow(
            name="ep1", bundle_id=bundle.id, auth_modes=["oauth"], profile="oauth_only"
        )
        ep2 = EndpointRow(
            name="ep2", bundle_id=bundle.id, auth_modes=["oauth"], profile="oauth_only"
        )
        db.add_all([ep1, ep2])
        await db.commit()

    async with serving(
        engine,
        redis,
        settings=hermetic_settings(public_url=PUBLIC_URL),
        base_url=PUBLIC_URL,
        follow_redirects=False,
        client_metadata_fetcher=FakeClientMetadataFetcher(),
        clock=ManualClock(utcnow()),  # moved only by the tests that need time to pass
    ) as (http, app):
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
    assert "client_secret" not in body  # public client by default
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
        assert resp.status_code == 200  # consent page
        assert "Authorize access" in resp.text
        token = resp.text.split('name="token" value="')[1].split('"')[0]
        resp = await http.post("/oauth/consent", data={"token": token, "action": "approve"})
    assert resp.status_code == 302, resp.text
    location = urlparse(resp.headers["location"])
    query = parse_qs(location.query)
    assert query["state"] == ["st4te"]
    return query["code"][0]


def _issuer(app, uow) -> TokenIssuer:
    c = app.state.container
    return TokenIssuer(
        uow, TokenPolicy(), clock=c.clock, generator=c.secret_generator, hasher=c.secret_hasher
    )


def _code_grant(app, uow) -> AuthorizationCodeGrant:
    c = app.state.container
    return AuthorizationCodeGrant(uow, _issuer(app, uow), c.clock, c.secret_hasher)


def _refresh_grant(app, uow) -> RefreshTokenGrant:
    c = app.state.container
    return RefreshTokenGrant(uow, _issuer(app, uow), c.clock, c.secret_hasher)


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
    """AUTH-1: AS metadata + per-endpoint protected-resource metadata."""
    http, app, user = oauth_env
    meta = (await http.get("/.well-known/oauth-authorization-server")).json()
    assert meta["issuer"] == PUBLIC_URL
    assert meta["code_challenge_methods_supported"] == ["S256"]

    prm = (await http.get("/.well-known/oauth-protected-resource/ep1/mcp")).json()
    assert prm["resource"] == f"{PUBLIC_URL}/ep1/mcp"
    assert prm["authorization_servers"] == [PUBLIC_URL]


async def test_full_pkce_flow_and_mcp_call(oauth_env):
    """AUTH-2/3/4/10/11 + EP-3a happy path down to an authenticated initialize."""
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
    """AUTH-11: persistent consent."""
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
    """EP-3a/AUTH-10: a token for ep1 is rejected at ep2 with the 401 challenge."""
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
    """AUTH-3: bad verifier rejected; code burns on first use."""
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
    """AUTH-4: refresh rotates; the old refresh token stops working."""
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
        rows = (await db.execute(select(OAuthAccessTokenRow))).scalars().all()
    assert any(r.revoked for r in rows)


async def test_token_endpoint_honours_registered_grant_types(oauth_env):
    """AUTH-4: a client registered for the code grant alone may not refresh (unauthorized)."""
    http, app, user = oauth_env
    resp = await http.post(
        "/oauth/register",
        json={
            "redirect_uris": ["https://client.example/cb"],
            "grant_types": ["authorization_code"],
        },
    )
    assert resp.status_code == 201, resp.text
    client_id = resp.json()["client_id"]
    verifier, challenge = make_pkce()
    code = await _authorize(http, client_id, challenge, f"{PUBLIC_URL}/ep1/mcp")
    tokens = await _exchange(http, client_id, code, verifier)

    refused = await http.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": client_id,
        },
    )
    assert refused.status_code == 400
    assert refused.json()["error"] == "unauthorized_client"


async def test_authorize_refuses_a_client_without_the_code_grant(oauth_env):
    """AUTH-4: a client registered only for refresh_token cannot start the code flow."""
    http, app, user = oauth_env
    resp = await http.post(
        "/oauth/register",
        json={"redirect_uris": ["https://client.example/cb"], "grant_types": ["refresh_token"]},
    )
    assert resp.status_code == 201, resp.text
    _verifier, challenge = make_pkce()
    resp = await http.get(
        "/oauth/authorize",
        params={
            "client_id": resp.json()["client_id"],
            "redirect_uri": "https://client.example/cb",
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": f"{PUBLIC_URL}/ep1/mcp",
        },
    )
    assert resp.status_code == 302  # the client is genuine, so it learns at its redirect URI
    assert parse_qs(urlparse(resp.headers["location"]).query)["error"] == ["unauthorized_client"]


async def test_token_lifetimes_follow_runtime_config(oauth_env):
    """AUTH-4: access_token_lifetime is read from runtime config when the pair is issued."""
    from bundlemcp.domain.config.config_entry import ConfigEntry

    http, app, user = oauth_env
    async with app.state.container.unit_of_work_factory.open() as uow:
        uow.config_entries.add(ConfigEntry(key="access_token_lifetime", value=120))
        await uow.commit()
    await app.state.container.runtime_config.flush()
    client_id = await _register_client(http)
    verifier, challenge = make_pkce()
    code = await _authorize(http, client_id, challenge, f"{PUBLIC_URL}/ep1/mcp")
    tokens = await _exchange(http, client_id, code, verifier)
    assert tokens["expires_in"] == 120


async def test_tokens_expire_by_the_clock(oauth_env):
    """AUTH-4: an access token dies at its lifetime; a refresh token at its own, longer one."""
    from datetime import timedelta

    http, app, user = oauth_env
    clock = app.state.container.clock
    client_id = await _register_client(http)
    verifier, challenge = make_pkce()
    code = await _authorize(http, client_id, challenge, f"{PUBLIC_URL}/ep1/mcp")
    tokens = await _exchange(http, client_id, code, verifier)
    service = {"Authorization": f"Bearer {SERVICE_KEY}"}

    def introspect(token):
        return http.post("/oauth/introspect", data={"token": token}, headers=service)

    assert (await introspect(tokens["access_token"])).json()["active"] is True
    clock.advance(timedelta(hours=1, seconds=1))
    assert (await introspect(tokens["access_token"])).json() == {"active": False}

    refreshed = await http.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": client_id,
        },
    )
    assert refreshed.status_code == 200  # the refresh token has a week
    clock.advance(timedelta(days=7, seconds=1))
    stale = await http.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refreshed.json()["refresh_token"],
            "client_id": client_id,
        },
    )
    assert stale.status_code == 400 and stale.json()["error"] == "invalid_grant"


async def test_introspection_requires_service_key(oauth_env):
    """AUTH-5/UPS-31."""
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

    # RFC 7662 client auth ("client credentials"): the service key may
    # arrive as the HTTP Basic client secret — what introspecting upstreams send.
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

    # gateway API keys introspect as active with the identity format,
    # so introspecting upstreams can serve api_key callers
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
    """AUTH-6."""
    http, app, user = oauth_env
    client_id = await _register_client(http)
    verifier, challenge = make_pkce()
    code = await _authorize(http, client_id, challenge, f"{PUBLIC_URL}/ep1/mcp")
    tokens = await _exchange(http, client_id, code, verifier)

    mcp_call = {
        "headers": {"Authorization": f"Bearer {tokens['access_token']}"},
        "json": {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    }
    # RFC 7009 2.1: the client authenticates; without it nothing is revoked
    anonymous = await http.post("/oauth/revoke", data={"token": tokens["access_token"]})
    assert anonymous.status_code == 401 and anonymous.json()["error"] == "invalid_client"
    assert (await http.post("/ep1/mcp", **mcp_call)).status_code == 200

    # another client cannot revoke it either, and learns nothing
    other = await _register_client(http)
    foreign = await http.post(
        "/oauth/revoke", data={"token": tokens["access_token"], "client_id": other}
    )
    assert foreign.status_code == 200
    assert (await http.post("/ep1/mcp", **mcp_call)).status_code == 200

    revoked = await http.post(
        "/oauth/revoke", data={"token": tokens["access_token"], "client_id": client_id}
    )
    assert revoked.status_code == 200
    assert (await http.post("/ep1/mcp", **mcp_call)).status_code == 401
    # a refresh token revokes the pair too, and an unknown token is a quiet 200
    assert (
        await http.post("/oauth/revoke", data={"token": "bmcp_rt_nothing", "client_id": client_id})
    ).status_code == 200


async def test_authorize_requires_login_redirect(oauth_env):
    """AUTH-3: no browser session -> redirect into /login with next."""
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


async def test_unauthenticated_authorize_writes_no_client_mirror(oauth_env):
    """AUTH-13: before login the document is only checked; the mirror is written on approval."""
    from bundlemcp.infrastructure.postgres.rows.oauth_client_row import OAuthClientRow

    http, app, user = oauth_env
    http.cookies.delete(SESSION_COOKIE)
    _, challenge = make_pkce()
    resp = await http.get(
        "/oauth/authorize",
        params={
            "client_id": CIMD_CLIENT_ID,
            "redirect_uri": "https://client.example/cb",
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": f"{PUBLIC_URL}/ep1/mcp",
        },
    )
    assert resp.status_code == 302 and resp.headers["location"].startswith("/login?next=")
    async with app.state.container.session_factory() as db:
        rows = (await db.execute(select(OAuthClientRow))).scalars().all()
    assert all(r.client_id != CIMD_CLIENT_ID for r in rows)


async def test_missing_resource_rejected(oauth_env):
    """AUTH-10: resource is required and must be a bundlemcp endpoint."""
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


async def test_authorization_responses_carry_the_issuer(oauth_env):
    """AUTH-14: code and error redirects carry iss, and the metadata says so."""
    http, app, user = oauth_env
    client_id = await _register_client(http)
    verifier, challenge = make_pkce()
    params = {
        "client_id": client_id,
        "redirect_uri": "https://client.example/cb",
        "response_type": "code",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": "st4te",
        "resource": f"{PUBLIC_URL}/ep1/mcp",
    }
    resp = await http.get("/oauth/authorize", params=params)
    token = resp.text.split('name="token" value="')[1].split('"')[0]
    approved = await http.post("/oauth/consent", data={"token": token, "action": "approve"})
    assert parse_qs(urlparse(approved.headers["location"]).query)["iss"] == [PUBLIC_URL]

    resp = await http.get("/oauth/authorize", params={**params, "resource": "https://elsewhere/x"})
    query = parse_qs(urlparse(resp.headers["location"]).query)
    assert query["error"] == ["invalid_target"] and query["iss"] == [PUBLIC_URL]

    meta = (await http.get("/.well-known/oauth-authorization-server")).json()
    assert meta["authorization_response_iss_parameter_supported"] is True
    assert meta["client_id_metadata_document_supported"] is True


async def test_client_id_metadata_document_needs_no_registration(oauth_env):
    """AUTH-13: an https client_id is resolved from its document and works end to end."""
    http, app, user = oauth_env
    verifier, challenge = make_pkce()
    code = await _authorize(http, CIMD_CLIENT_ID, challenge, f"{PUBLIC_URL}/ep1/mcp")
    tokens = await _exchange(http, CIMD_CLIENT_ID, code, verifier)
    assert tokens["access_token"].startswith("bmcp_")
    assert app.state.container.client_metadata.fetches >= 1

    unknown = await http.get(
        "/oauth/authorize",
        params={
            "client_id": "https://client.example/other.json",
            "redirect_uri": "https://client.example/cb",
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": f"{PUBLIC_URL}/ep1/mcp",
        },
    )
    assert unknown.status_code == 400  # never redirect for a client that cannot be resolved


async def test_registration_records_application_type(oauth_env):
    """AUTH-2: application_type is accepted, stored and echoed."""
    http, app, user = oauth_env
    resp = await http.post(
        "/oauth/register",
        json={
            "redirect_uris": ["http://localhost:3000/cb"],
            "client_name": "Native",
            "application_type": "native",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["application_type"] == "native"
    bad = await http.post(
        "/oauth/register",
        json={"redirect_uris": ["https://client.example/cb"], "application_type": "desktop"},
    )
    assert bad.status_code == 400
    assert bad.json()["error"] == "invalid_client_metadata"
    assert "application_type" in bad.json()["error_description"]


async def test_registration_refuses_grants_the_server_does_not_serve(oauth_env):
    """AUTH-2: OAuth 2.1 dropped the implicit grant; asking for it is invalid_client_metadata."""
    http, app, user = oauth_env
    resp = await http.post(
        "/oauth/register",
        json={"redirect_uris": ["https://client.example/cb"], "grant_types": ["implicit"]},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "invalid_client_metadata"
    assert body["error_description"].startswith("grant_types")


async def test_registration_answers_a_malformed_body_in_protocol_terms(oauth_env):
    """AUTH-2: a body FastAPI cannot parse is still an RFC 7591 error, never a bare 422."""
    http, app, user = oauth_env
    resp = await http.post(
        "/oauth/register", content=b"not json", headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_client_metadata"


async def test_registration_rejects_a_bad_redirect_uri_with_its_own_error(oauth_env):
    """AUTH-2: a redirect URI that is neither https nor localhost is invalid_redirect_uri."""
    http, app, user = oauth_env
    resp = await http.post("/oauth/register", json={"redirect_uris": ["http://client.example/cb"]})
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_redirect_uri"


async def test_code_burn_is_a_compare_and_set(oauth_env):
    """AUTH-3: a code another transaction burned between the read and the burn is refused.

    The race is reproduced without concurrency: the code is read into the
    session (as a racing request would), then the row changes underneath that
    stale read, then the grant proceeds from the stale object.
    """
    from bundlemcp.application.errors import OAuthError
    from bundlemcp.application.oauth_server import TokenRequest
    from bundlemcp.infrastructure.postgres.rows.oauth_authorization_code_row import (
        OAuthAuthorizationCodeRow,
    )
    from sqlalchemy import update

    http, app, user = oauth_env
    client_id = await _register_client(http)
    verifier, challenge = make_pkce()
    code = await _authorize(http, client_id, challenge, f"{PUBLIC_URL}/ep1/mcp")

    async with app.state.container.unit_of_work_factory.open() as uow:
        db = uow.session
        stale = await uow.authorization_codes.get(hash_token(code))
        assert stale is not None and not stale.used
        await db.execute(  # the other redemption wins the race
            update(OAuthAuthorizationCodeRow)
            .where(OAuthAuthorizationCodeRow.code_hash == stale.code_hash)
            .values(used=True)
            .execution_options(synchronize_session=False)
        )
        client = await uow.oauth_clients.get(client_id)
        request = TokenRequest(
            grant_type="authorization_code",
            code=code,
            redirect_uri="https://client.example/cb",
            code_verifier=verifier,
        )
        with pytest.raises(OAuthError) as excinfo:
            await _code_grant(app, uow).exchange(client, request)
        assert excinfo.value.code == OAuthErrorCode.INVALID_GRANT
        rows = (await db.execute(select(OAuthAccessTokenRow))).scalars().all()
    assert rows == []


async def test_refresh_rotation_is_a_compare_and_set(oauth_env):
    """AUTH-4: a refresh token rotated between the read and the rotation is a replay."""
    from bundlemcp.application.errors import OAuthError
    from bundlemcp.application.oauth_server import TokenRequest
    from sqlalchemy import update

    http, app, user = oauth_env
    client_id = await _register_client(http)
    verifier, challenge = make_pkce()
    code = await _authorize(http, client_id, challenge, f"{PUBLIC_URL}/ep1/mcp")
    tokens = await _exchange(http, client_id, code, verifier)

    async with app.state.container.unit_of_work_factory.open() as uow:
        db = uow.session
        stale = await uow.oauth_tokens.by_refresh_hash(hash_token(tokens["refresh_token"]))
        assert stale is not None and not stale.revoked
        await db.execute(
            update(OAuthAccessTokenRow)
            .where(OAuthAccessTokenRow.id == stale.id)
            .values(revoked=True)
            .execution_options(synchronize_session=False)
        )
        client = await uow.oauth_clients.get(client_id)
        request = TokenRequest(grant_type="refresh_token", refresh_token=tokens["refresh_token"])
        with pytest.raises(OAuthError) as excinfo:
            await _refresh_grant(app, uow).exchange(client, request)
        assert excinfo.value.code == OAuthErrorCode.INVALID_GRANT
        rows = (await db.execute(select(OAuthAccessTokenRow))).scalars().all()
    assert len(rows) == 1 and rows[0].revoked


async def test_refresh_replay_revokes_the_family(oauth_env):
    """AUTH-4 / RFC 9700 4.14.2: replaying a rotated refresh token revokes every descendant."""
    http, app, user = oauth_env
    client_id = await _register_client(http)
    verifier, challenge = make_pkce()
    code = await _authorize(http, client_id, challenge, f"{PUBLIC_URL}/ep1/mcp")
    first = await _exchange(http, client_id, code, verifier)

    def refresh(token: str):
        return http.post(
            "/oauth/token",
            data={"grant_type": "refresh_token", "refresh_token": token, "client_id": client_id},
        )

    second = (await refresh(first["refresh_token"])).json()
    third = (await refresh(second["refresh_token"])).json()

    # the newest access token works until the replay
    ok = await http.post(
        "/ep1/mcp",
        headers={"Authorization": f"Bearer {third['access_token']}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert ok.status_code == 200

    replay = await refresh(first["refresh_token"])
    assert replay.status_code == 400 and replay.json()["error"] == "invalid_grant"

    # ... and afterwards the whole family is dead, the newest pair included
    async with app.state.container.session_factory() as db:
        rows = (await db.execute(select(OAuthAccessTokenRow))).scalars().all()
    assert len(rows) == 3 and all(r.revoked for r in rows)
    assert len({r.family_id for r in rows}) == 1
    dead = await http.post(
        "/ep1/mcp",
        headers={"Authorization": f"Bearer {third['access_token']}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert dead.status_code == 401
    assert (await refresh(third["refresh_token"])).status_code == 400


async def test_redirect_uri_with_query_receives_the_code(oauth_env):
    """RFC 6749 3.1.2: a registered redirect URI may carry a query; the code is merged into it."""
    http, app, user = oauth_env
    redirect_uri = "https://client.example/cb?tenant=x"
    resp = await http.post(
        "/oauth/register", json={"redirect_uris": [redirect_uri], "client_name": "Tenant"}
    )
    client_id = resp.json()["client_id"]
    _, challenge = make_pkce()
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": "st4te",
        "resource": f"{PUBLIC_URL}/ep1/mcp",
    }
    consent = await http.get("/oauth/authorize", params=params)
    token = consent.text.split('name="token" value="')[1].split('"')[0]
    approved = await http.post("/oauth/consent", data={"token": token, "action": "approve"})
    location = urlparse(approved.headers["location"])
    query = parse_qs(location.query)
    assert location.path == "/cb"
    assert query["tenant"] == ["x"] and query["state"] == ["st4te"] and query["iss"] == [PUBLIC_URL]
    assert query["code"]

    denied = await http.get(
        "/oauth/authorize", params={**params, "resource": "https://elsewhere/x"}
    )
    query = parse_qs(urlparse(denied.headers["location"]).query)
    assert query["tenant"] == ["x"] and query["error"] == ["invalid_target"]


async def test_locked_out_client_gets_no_exchange(oauth_env):
    """EP-20: once locked out, even a correct redemption is refused before it is evaluated."""
    http, app, user = oauth_env
    client_id = await _register_client(http)
    verifier, challenge = make_pkce()
    code = await _authorize(http, client_id, challenge, f"{PUBLIC_URL}/ep1/mcp")
    limit = app.state.container.settings.auth_failure_limit
    for attempt in range(limit + 1):
        bad = await http.post(
            "/oauth/token",
            data={"grant_type": "authorization_code", "code": "x", "client_id": "nobody"},
        )
        assert bad.status_code == (401 if attempt < limit else 429)
    locked = await http.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://client.example/cb",
            "code_verifier": verifier,
            "client_id": client_id,
        },
    )
    assert locked.status_code == 429 and "Retry-After" in locked.headers
    # the code was never looked at, so it is still redeemable once the lock lifts
    app.state.container.redis.advance(app.state.container.settings.auth_failure_window)
    tokens = await _exchange(http, client_id, code, verifier)
    assert tokens["access_token"].startswith("bmcp_at_")


async def test_registration_rate_limit_keys_on_the_forwarded_client_ip(engine, redis):
    """AUTH-12: behind a trusted proxy the limit is per original client, not per proxy."""
    settings = hermetic_settings(public_url=PUBLIC_URL, trusted_proxies=["127.0.0.0/8"])
    assert (settings.dcr_rate_limit, settings.dcr_rate_window) == (10, 3600)
    body = {"redirect_uris": ["https://client.example/cb"], "client_name": "C"}
    async with serving(engine, redis, settings=settings, base_url=PUBLIC_URL) as (http, _app):
        for _ in range(settings.dcr_rate_limit):
            ok = await http.post(
                "/oauth/register", json=body, headers={"X-Forwarded-For": "203.0.113.7"}
            )
            assert ok.status_code == 201
        exhausted = await http.post(
            "/oauth/register", json=body, headers={"X-Forwarded-For": "203.0.113.7"}
        )
        assert exhausted.status_code == 429
        assert exhausted.json()["error"] == "too_many_requests"
        other = await http.post(
            "/oauth/register", json=body, headers={"X-Forwarded-For": "203.0.113.8"}
        )
        assert other.status_code == 201


ALLOWED_REDIRECTS = ["https://claude.ai/api/mcp/auth_callback", "https://*.client.example/cb"]


async def test_registration_allow_list_refuses_unlisted_redirect_uris(engine, redis):
    """AUTH-2: with an allow-list configured, an unlisted redirect URI is invalid_redirect_uri."""
    settings = hermetic_settings(public_url=PUBLIC_URL, dcr_allowed_redirect_uris=ALLOWED_REDIRECTS)
    async with serving(engine, redis, settings=settings, base_url=PUBLIC_URL) as (http, _app):
        for listed in ("https://claude.ai/api/mcp/auth_callback", "https://app.client.example/cb"):
            ok = await http.post("/oauth/register", json={"redirect_uris": [listed]})
            assert ok.status_code == 201, (listed, ok.text)
        for unlisted in (
            "https://evil.example/cb",
            "https://a.b.client.example/cb",
            "https://claude.ai/api/mcp/auth_callback/x",
        ):
            refused = await http.post(
                "/oauth/register",
                json={"redirect_uris": ["https://claude.ai/api/mcp/auth_callback", unlisted]},
            )
            assert refused.status_code == 400, unlisted
            assert refused.json()["error"] == "invalid_redirect_uri"


async def test_registration_without_allow_list_accepts_any_https_redirect_uri(engine, redis):
    """AUTH-2: the default empty allow-list keeps every https redirect URI acceptable."""
    async with serving(engine, redis, settings=hermetic_settings(public_url=PUBLIC_URL)) as (
        http,
        _app,
    ):
        resp = await http.post(
            "/oauth/register", json={"redirect_uris": ["https://evil.example/cb"]}
        )
        assert resp.status_code == 201


async def test_registration_rate_limit_and_window_are_configurable(engine, redis):
    """AUTH-12: the per-IP registration limit and its window come from settings."""
    settings = hermetic_settings(public_url=PUBLIC_URL, dcr_rate_limit=2, dcr_rate_window=60)
    body = {"redirect_uris": ["https://client.example/cb"]}
    async with serving(engine, redis, settings=settings, base_url=PUBLIC_URL) as (http, _app):
        assert [(await http.post("/oauth/register", json=body)).status_code for _ in range(3)] == [
            201,
            201,
            429,
        ]
        redis.advance(60)  # the next window opens a fresh budget
        assert (await http.post("/oauth/register", json=body)).status_code == 201


async def test_allow_listed_registrations_skip_the_per_ip_limit_not_the_global_quota(engine, redis):
    """AUTH-12/SEC-8: allow-listed redirect URIs skip the per-IP budget; the global quota holds."""
    settings = hermetic_settings(
        public_url=PUBLIC_URL,
        dcr_allowed_redirect_uris=ALLOWED_REDIRECTS,
        dcr_rate_limit=1,
        dcr_max_unused_clients=3,
    )
    body = {"redirect_uris": ["https://claude.ai/api/mcp/auth_callback"]}
    async with serving(engine, redis, settings=settings, base_url=PUBLIC_URL) as (http, _app):
        for _ in range(3):  # three from one IP, past its budget of one
            assert (await http.post("/oauth/register", json=body)).status_code == 201
        quota = await http.post("/oauth/register", json=body)
        assert quota.status_code == 429
        assert quota.json()["error"] == "too_many_requests"
        assert "not been used" in quota.json()["error_description"]


async def test_global_quota_counts_only_clients_that_never_obtained_a_token(engine, redis):
    """SEC-8: a client that obtained a token no longer counts against the unused-client quota."""
    from bundlemcp.infrastructure.postgres.rows.oauth_client_row import OAuthClientRow

    settings = hermetic_settings(public_url=PUBLIC_URL, dcr_max_unused_clients=1)
    body = {"redirect_uris": ["https://client.example/cb"]}
    async with serving(engine, redis, settings=settings, base_url=PUBLIC_URL) as (http, app):
        first = await http.post("/oauth/register", json=body)
        assert first.status_code == 201
        assert (await http.post("/oauth/register", json=body)).status_code == 429
        async with app.state.container.session_factory() as db:
            row = await db.get(OAuthClientRow, first.json()["client_id"])
            row.last_used_at = utcnow()
            await db.commit()
        assert (await http.post("/oauth/register", json=body)).status_code == 201


async def test_metadata_document_redirect_uris_must_be_on_the_allow_list(engine, redis):
    """AUTH-13: a metadata document declaring an unlisted redirect URI is refused at authorize."""
    _, challenge = make_pkce()
    params = {
        "client_id": CIMD_CLIENT_ID,
        "redirect_uri": "https://client.example/cb",
        "response_type": "code",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": f"{PUBLIC_URL}/ep1/mcp",
    }
    for allowed, status in ((["https://claude.ai/cb"], 400), (["https://client.example/cb"], 302)):
        settings = hermetic_settings(public_url=PUBLIC_URL, dcr_allowed_redirect_uris=allowed)
        async with serving(
            engine,
            redis,
            settings=settings,
            base_url=PUBLIC_URL,
            follow_redirects=False,
            client_metadata_fetcher=FakeClientMetadataFetcher(),
        ) as (http, _app):
            resp = await http.get("/oauth/authorize", params=params)
            assert resp.status_code == status, (allowed, resp.text)


def test_malformed_allow_list_entries_are_refused_at_startup():
    """AUTH-2: a pattern that is not an exact URI or a leading-label wildcard fails settings."""
    from pydantic import ValidationError

    for bad in ("claude.ai/cb", "https://*.com/cb", "https://a.*.example.com/cb", "https://x/*"):
        with pytest.raises(ValidationError):
            hermetic_settings(dcr_allowed_redirect_uris=[bad])


# Consent page CSP: browsers apply form-action to the redirect that answers a form
# post, so the consent page admits its own authorization's redirect URI and nothing else.

SAME_ORIGIN_POLICY = (
    "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; form-action 'self'"
)


async def _register_redirect(http, redirect_uri: str, name: str = "TestClient") -> str:
    resp = await http.post(
        "/oauth/register", json={"redirect_uris": [redirect_uri], "client_name": name}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["client_id"]


async def _consent_page(http, client_id: str, redirect_uri: str):
    _, challenge = make_pkce()
    page = await http.get(
        "/oauth/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "st4te",
            "resource": f"{PUBLIC_URL}/ep1/mcp",
        },
    )
    assert page.status_code == 200, page.text
    token = page.text.split('name="token" value="')[1].split('"')[0]
    return page, token


async def test_consent_page_form_action_admits_only_its_redirect_uri(oauth_env):
    """SEC-6: form-action is 'self' plus exactly this authorization's redirect URI."""
    http, _, _ = oauth_env
    client_id = await _register_redirect(http, "https://client.example/api/mcp/auth_callback")
    await _register_redirect(http, "https://other.example/cb", name="Other")

    page, _ = await _consent_page(http, client_id, "https://client.example/api/mcp/auth_callback")

    csp = page.headers["content-security-policy"]
    assert csp == f"{SAME_ORIGIN_POLICY} https://client.example/api/mcp/auth_callback"
    assert "other.example" not in csp
    assert page.headers["x-frame-options"] == "DENY"


async def test_consent_page_source_drops_the_redirect_query(oauth_env):
    """SEC-6: the source expression names the callback without its query, which still
    reaches the client merged with the code."""
    http, _, _ = oauth_env
    redirect_uri = "https://client.example/cb?tenant=a"
    client_id = await _register_redirect(http, redirect_uri)

    page, token = await _consent_page(http, client_id, redirect_uri)
    approved = await http.post("/oauth/consent", data={"token": token, "action": "approve"})

    csp = page.headers["content-security-policy"]
    assert csp == f"{SAME_ORIGIN_POLICY} https://client.example/cb"
    assert approved.status_code == 302
    query = parse_qs(urlparse(approved.headers["location"]).query)
    assert query["tenant"] == ["a"] and query["state"] == ["st4te"] and query["code"]


async def test_consent_deny_redirects_access_denied(oauth_env):
    """AUTH-11: Deny reaches the client's redirect URI as error=access_denied."""
    http, _, _ = oauth_env
    client_id = await _register_redirect(http, "https://client.example/cb")
    _, token = await _consent_page(http, client_id, "https://client.example/cb")

    denied = await http.post("/oauth/consent", data={"token": token, "action": "deny"})

    assert denied.status_code == 302
    location = urlparse(denied.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == "https://client.example/cb"
    query = parse_qs(location.query)
    assert query["error"] == ["access_denied"] and query["state"] == ["st4te"]
    assert query["iss"] == [PUBLIC_URL]


@pytest.mark.parametrize("action, expected", [("approve", "code"), ("deny", "error")])
async def test_unexpressible_redirect_uri_keeps_page_same_origin(oauth_env, action, expected):
    """SEC-6: a redirect URI that cannot be a source expression leaves form-action 'self',
    and the consent answer is a same-origin page linking to the client."""
    http, _, _ = oauth_env
    redirect_uri = "https://client.example/cb;v=1"
    client_id = await _register_redirect(http, redirect_uri)

    page, token = await _consent_page(http, client_id, redirect_uri)
    answer = await http.post("/oauth/consent", data={"token": token, "action": action})

    assert page.headers["content-security-policy"] == SAME_ORIGIN_POLICY
    assert answer.status_code == 200
    assert answer.headers["content-security-policy"] == SAME_ORIGIN_POLICY
    link = answer.text.split('class="continue" href="')[1].split('"')[0].replace("&amp;", "&")
    assert link.startswith(redirect_uri)
    query = parse_qs(urlparse(link).query)
    assert query[expected] and query["state"] == ["st4te"]


def test_other_auth_pages_stay_same_origin():
    """SEC-6: pages that never redirect off-origin keep form-action 'self' alone."""
    assert page_headers() == {
        "Content-Security-Policy": SAME_ORIGIN_POLICY,
        "X-Frame-Options": "DENY",
        "Cache-Control": "no-store",
    }


async def test_auth20_authorize_sends_a_deactivated_users_session_back_to_login(oauth_env):
    """AUTH-20: a deactivated user's unexpired session no longer counts at authorize.

    Authorize sends them to /login, which refuses a deactivated user (see the OIDC tests),
    so no code is ever issued to them.
    """
    http, app, user = oauth_env
    client_id = await _register_client(http)
    _, challenge = make_pkce()
    session = http.cookies.get(SESSION_COOKIE)
    http.cookies.delete(SESSION_COOKIE)  # the admin action is the service key's, not the user's
    resp = await http.post(
        f"/api/v1/users/{user.id}:deactivate",
        headers={"Authorization": f"Bearer {SERVICE_KEY}"},
    )
    assert resp.status_code == 200
    http.cookies.set(SESSION_COOKIE, session)  # the deactivated user's own, still unexpired
    authorize = await http.get(
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
    assert authorize.status_code == 302
    assert authorize.headers["location"].startswith("/login?next=")


INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-11-25", "capabilities": {}},
}


async def _access_token(http) -> tuple[str, str]:
    """An access token for ep1, and the client it was issued to."""
    client_id = await _register_client(http)
    verifier, challenge = make_pkce()
    code = await _authorize(http, client_id, challenge, f"{PUBLIC_URL}/ep1/mcp")
    return (await _exchange(http, client_id, code, verifier))["access_token"], client_id


def _challenge(resp) -> str:
    assert resp.status_code == 401
    return resp.headers["WWW-Authenticate"]


async def test_ep3a_a_token_for_another_endpoint_is_an_invalid_token(oauth_env):
    """EP-3a: refused at ep2 with error="invalid_token" and ep2's own metadata."""
    http, app, user = oauth_env
    token, _ = await _access_token(http)
    resp = await http.post(
        "/ep2/mcp", headers={"Authorization": f"Bearer {token}"}, json=INITIALIZE
    )
    challenge = _challenge(resp)
    assert 'error="invalid_token"' in challenge
    assert f'resource_metadata="{PUBLIC_URL}/.well-known/oauth-protected-resource/ep2/mcp"' in (
        challenge
    )


async def test_ep3a_expired_unknown_and_revoked_tokens_are_invalid(oauth_env):
    """EP-3a: every refusal reason gets the same invalid_token challenge."""
    from datetime import timedelta

    http, app, user = oauth_env
    unknown = await http.post(
        "/ep1/mcp", headers={"Authorization": "Bearer bmcp_at_unknown"}, json=INITIALIZE
    )
    assert 'error="invalid_token"' in _challenge(unknown)

    revoked, client_id = await _access_token(http)
    await http.post("/oauth/revoke", data={"token": revoked, "client_id": client_id})
    resp = await http.post(
        "/ep1/mcp", headers={"Authorization": f"Bearer {revoked}"}, json=INITIALIZE
    )
    assert 'error="invalid_token"' in _challenge(resp)

    expiring, _ = await _access_token(http)
    app.state.container.clock.advance(timedelta(hours=1, seconds=1))
    resp = await http.post(
        "/ep1/mcp", headers={"Authorization": f"Bearer {expiring}"}, json=INITIALIZE
    )
    assert 'error="invalid_token"' in _challenge(resp)


async def test_ep3a_no_credentials_keeps_the_plain_challenge(oauth_env):
    """EP-3a: a request with no Authorization header gets resource_metadata and no error."""
    http, app, user = oauth_env
    challenge = _challenge(await http.post("/ep1/mcp", json=INITIALIZE))
    assert "resource_metadata=" in challenge
    assert "error=" not in challenge


async def test_ep3a_a_refused_bearer_still_counts_toward_the_lockout(oauth_env):
    """EP-3a/EP-20: the invalid_token answer is still an authentication failure."""
    http, app, user = oauth_env
    registry = app.state.container.metrics.registry
    before = registry.get_sample_value("bundlemcp_auth_failures_total") or 0
    await http.post("/ep1/mcp", headers={"Authorization": "Bearer bmcp_at_x"}, json=INITIALIZE)
    assert registry.get_sample_value("bundlemcp_auth_failures_total") == before + 1


def test_ep3a_only_a_bearer_with_a_value_counts_as_presented():
    from bundlemcp.api.mcp.routing.authentication import presents_bearer

    assert presents_bearer("Bearer abc") and presents_bearer("bearer abc")
    assert not presents_bearer(None)
    assert not presents_bearer("Bearer ")
    assert not presents_bearer("Basic abc")


async def _code_for_ep1(http) -> tuple[str, str, str]:
    client_id = await _register_client(http)
    verifier, challenge = make_pkce()
    code = await _authorize(http, client_id, challenge, f"{PUBLIC_URL}/ep1/mcp")
    return client_id, code, verifier


def _code_form(client_id: str, code: str, verifier: str, **extra: str) -> dict:
    return {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": "https://client.example/cb",
        "code_verifier": verifier,
        "client_id": client_id,
        **extra,
    }


async def _works_at(http, token: str, endpoint: str) -> bool:
    resp = await http.post(
        f"/{endpoint}/mcp", headers={"Authorization": f"Bearer {token}"}, json=INITIALIZE
    )
    return resp.status_code == 200


@pytest.mark.parametrize("resource", [None, f"{PUBLIC_URL}/ep1/mcp"], ids=["absent", "matching"])
async def test_auth10_code_redeemed_for_its_own_endpoint(oauth_env, resource):
    """AUTH-10: without resource, or naming the code's endpoint, the tokens are bound to ep1."""
    http, app, user = oauth_env
    client_id, code, verifier = await _code_for_ep1(http)
    extra = {"resource": resource} if resource else {}
    resp = await http.post("/oauth/token", data=_code_form(client_id, code, verifier, **extra))
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    assert await _works_at(http, token, "ep1")
    assert not await _works_at(http, token, "ep2")


@pytest.mark.parametrize(
    "resource",
    [f"{PUBLIC_URL}/ep2/mcp", "https://elsewhere.example/ep1/mcp", f"{PUBLIC_URL}/nope/mcp"],
    ids=["other-endpoint", "not-this-gateway", "unknown-endpoint"],
)
async def test_auth10_code_with_another_resource_is_invalid_target(oauth_env, resource):
    """AUTH-10: a mismatched resource issues nothing and leaves the code redeemable."""
    http, app, user = oauth_env
    client_id, code, verifier = await _code_for_ep1(http)
    refused = await http.post(
        "/oauth/token", data=_code_form(client_id, code, verifier, resource=resource)
    )
    assert refused.status_code == 400
    assert refused.json()["error"] == "invalid_target"
    assert (await http.post("/oauth/token", data=_code_form(client_id, code, verifier))).is_success


async def test_auth10_refresh_with_another_resource_neither_rotates_nor_revokes(oauth_env):
    """AUTH-10: the refresh token survives a refused resource and still refreshes for ep1."""
    http, app, user = oauth_env
    client_id, code, verifier = await _code_for_ep1(http)
    tokens = (await http.post("/oauth/token", data=_code_form(client_id, code, verifier))).json()
    refresh = {
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"],
        "client_id": client_id,
    }
    refused = await http.post("/oauth/token", data={**refresh, "resource": f"{PUBLIC_URL}/ep2/mcp"})
    assert refused.status_code == 400 and refused.json()["error"] == "invalid_target"
    assert await _works_at(http, tokens["access_token"], "ep1")  # nothing was revoked

    matching = await http.post(
        "/oauth/token", data={**refresh, "resource": f"{PUBLIC_URL}/ep1/mcp"}
    )
    assert matching.status_code == 200, matching.text
    assert await _works_at(http, matching.json()["access_token"], "ep1")


async def test_auth11_a_user_lists_and_revokes_their_own_consent(oauth_env):
    """AUTH-11: /me/consents lists the user's consent; revoking it kills its tokens too."""
    http, app, user = oauth_env
    token, client_id = await _access_token(http)
    listed = (await http.get("/api/v1/me/consents")).json()
    assert [(c["client_id"], c["endpoint_id"]) for c in listed] == [
        (client_id, listed[0]["endpoint_id"])
    ]
    resp = await http.delete(
        f"/api/v1/me/consents/{listed[0]['id']}", headers={"Origin": PUBLIC_URL}
    )
    assert resp.status_code == 204
    assert (await http.get("/api/v1/me/consents")).json() == []
    assert not await _works_at(http, token, "ep1")


async def test_auth11_self_service_consents_need_a_signed_in_person(oauth_env):
    """AUTH-11: a service key and an anonymous caller get 401; a cross-site delete gets 403."""
    http, app, user = oauth_env
    await _access_token(http)
    consent_id = (await http.get("/api/v1/me/consents")).json()[0]["id"]

    cross_site = await http.delete(
        f"/api/v1/me/consents/{consent_id}", headers={"Origin": "https://evil.example"}
    )
    assert cross_site.status_code == 403

    session = http.cookies.get(SESSION_COOKIE)
    http.cookies.delete(SESSION_COOKIE)
    assert (await http.get("/api/v1/me/consents")).status_code == 401
    as_service = {"Authorization": f"Bearer {SERVICE_KEY}"}
    assert (await http.get("/api/v1/me/consents", headers=as_service)).status_code == 401
    http.cookies.set(SESSION_COOKIE, session)
    assert len((await http.get("/api/v1/me/consents")).json()) == 1  # nothing was revoked


async def test_auth11_another_users_consent_answers_404(oauth_env):
    http, app, user = oauth_env
    resp = await http.delete(f"/api/v1/me/consents/{uuid.uuid4()}", headers={"Origin": PUBLIC_URL})
    assert resp.status_code == 404


def _cimd_authorize_params(client_id: str) -> dict[str, str]:
    _, challenge = make_pkce()
    return {
        "client_id": client_id,
        "redirect_uri": "https://client.example/cb",
        "response_type": "code",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": f"{PUBLIC_URL}/ep1/mcp",
    }


async def test_auth13_authorize_refuses_private_metadata_url(engine, redis):
    """AUTH-13: an unauthenticated authorize naming a document on a private address is refused
    by the real fetcher before it connects anywhere."""
    async with serving(
        engine,
        redis,
        settings=hermetic_settings(public_url=PUBLIC_URL),
        base_url=PUBLIC_URL,
        follow_redirects=False,
    ) as (http, _app):
        with capture_logs() as logs:
            resp = await http.get(
                "/oauth/authorize", params=_cimd_authorize_params("https://10.0.0.5/client.json")
            )
    assert resp.status_code == 400
    (failure,) = [e for e in logs if e["event"] == "cimd.fetch_failed"]
    assert failure["reason"] == "EgressDenied"


async def test_auth34_off_refuses_without_fetch(engine, redis):
    """AUTH-34: with metadata-document clients off, an https client_id is unknown and unfetched."""
    fetcher = FakeClientMetadataFetcher()
    settings = hermetic_settings(public_url=PUBLIC_URL, client_metadata_documents_enabled=False)
    async with serving(
        engine,
        redis,
        settings=settings,
        base_url=PUBLIC_URL,
        follow_redirects=False,
        client_metadata_fetcher=fetcher,
    ) as (http, _app):
        resp = await http.get("/oauth/authorize", params=_cimd_authorize_params(CIMD_CLIENT_ID))
    assert resp.status_code == 400
    assert fetcher.fetches == 0


async def test_auth34_off_advertised_in_metadata(engine, redis):
    """AUTH-34: turned off, the authorization server metadata says metadata documents are not
    supported."""
    settings = hermetic_settings(public_url=PUBLIC_URL, client_metadata_documents_enabled=False)
    async with serving(engine, redis, settings=settings) as (http, _app):
        meta = (await http.get("/.well-known/oauth-authorization-server")).json()
    assert meta["client_id_metadata_document_supported"] is False


async def test_auth34_default_on(engine, redis):
    """AUTH-34: by default metadata-document clients are accepted and advertised."""
    async with serving(engine, redis, settings=hermetic_settings(public_url=PUBLIC_URL)) as (
        http,
        _app,
    ):
        meta = (await http.get("/.well-known/oauth-authorization-server")).json()
    assert meta["client_id_metadata_document_supported"] is True


async def _client_count(app) -> int:
    from bundlemcp.infrastructure.postgres.rows.oauth_client_row import OAuthClientRow
    from sqlalchemy import func

    async with app.state.container.session_factory() as db:
        return (await db.execute(select(func.count()).select_from(OAuthClientRow))).scalar_one()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("redirect_uris", [f"https://client.example/cb{i}" for i in range(11)]),
        ("redirect_uris", ["https://client.example/" + "a" * (2049 - 23)]),
        ("client_name", "n" * 201),
        ("scope", "s" * 1001),
        ("grant_types", ["authorization_code"] * 11),
        ("response_types", ["code"] * 11),
    ],
)
async def test_auth2_oversized_metadata_refused(oauth_env, field, value):
    """AUTH-2: registration metadata over its bound is refused with invalid_client_metadata
    naming the field, and no client is stored."""
    http, app, _ = oauth_env
    body = {"redirect_uris": ["https://client.example/cb"], field: value}
    before = await _client_count(app)
    resp = await http.post("/oauth/register", json=body)
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "invalid_client_metadata"
    assert resp.json()["error_description"].startswith(field)
    assert await _client_count(app) == before


async def test_auth2_metadata_at_bounds_accepted(oauth_env):
    """AUTH-2: 10 redirect URIs (one of 2048 characters), a 200-character client_name and a
    1000-character scope are accepted."""
    http, _, _ = oauth_env
    long_uri = "https://client.example/" + "a" * (2048 - 23)
    assert len(long_uri) == 2048
    uris = [long_uri] + [f"https://client.example/cb{i}" for i in range(9)]
    resp = await http.post(
        "/oauth/register",
        json={"redirect_uris": uris, "client_name": "n" * 200, "scope": "s" * 1000},
    )
    assert resp.status_code == 201, resp.text
