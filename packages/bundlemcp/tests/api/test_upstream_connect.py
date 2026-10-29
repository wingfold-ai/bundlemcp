"""Upstream OAuth connect flow + management + UPS-30 tests (the upstreams spec)."""

import json
from contextlib import asynccontextmanager

from bundlemcp.api.oauth.session_cookie import SESSION_COOKIE
from bundlemcp.domain.access.api_key_kind import ApiKeyKind
from bundlemcp.domain.servers.identity_mode import IdentityMode
from bundlemcp.domain.servers.server_auth_mode import ServerAuthMode
from bundlemcp.domain.sessions.admin_session import AdminSession
from bundlemcp.domain.shared.secrets import display_prefix, hash_token
from bundlemcp.domain.upstream_oauth.upstream_metadata import UpstreamMetadata
from bundlemcp.domain.upstream_oauth.upstream_tokens import UpstreamTokens
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.api_key_row import ApiKeyRow
from bundlemcp.infrastructure.postgres.rows.bundle_row import BundleRow
from bundlemcp.infrastructure.postgres.rows.bundle_server_row import BundleServerRow
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.postgres.rows.upstream_oauth_client_row import UpstreamOAuthClientRow
from bundlemcp.infrastructure.postgres.rows.upstream_oauth_token_row import UpstreamOAuthTokenRow
from bundlemcp.infrastructure.postgres.rows.user_row import UserRow
from cryptography.fernet import Fernet
from sqlmodel import select

from tests.conftest import SERVICE_KEY, hermetic_settings, serving

KEY = Fernet.generate_key().decode()
PUBLIC_URL = "http://gw"


# Distinctive sentinels. The encrypted-at-rest assertion checks the plaintext is
# absent from the ciphertext, and a two-character value collides with random
# base64 often enough to fail roughly one run in twenty.
ACCESS_TOKEN = "access-token-plaintext-sentinel"
REFRESH_TOKEN = "refresh-token-plaintext-sentinel"
REFRESHED_ACCESS_TOKEN = "refreshed-access-token-plaintext-sentinel"


class FakeProvider:
    async def discover(self, server_url):
        return UpstreamMetadata(
            authorization_endpoint="https://idp/a",
            token_endpoint="https://idp/t",
            issuer="https://idp",
            authorization_response_iss_parameter_supported=True,
        )

    async def register(self, meta, *, redirect_uri, client_name):
        raise AssertionError("a client is already stored")

    def authorize_url(self, meta, *, client_id, redirect_uri, state, code_challenge, scope):
        return f"{meta.authorization_endpoint}?state={state}&client_id={client_id}"

    async def exchange(self, meta, *, code, redirect_uri, code_verifier, client_id, client_secret):
        return UpstreamTokens(
            access_token=ACCESS_TOKEN,
            refresh_token=REFRESH_TOKEN,
            expires_in=3600,
            account_hint="me@x",
        )

    async def refresh(self, meta, **kw):
        return UpstreamTokens(access_token=REFRESHED_ACCESS_TOKEN, expires_in=3600)

    async def client_credentials(self, meta, **kw):
        return UpstreamTokens(access_token="at-client", expires_in=3600)


@asynccontextmanager
async def _running(engine, redis, *, provider=None, bearer=None):
    """The gateway with a fake upstream authorization server, and a client at the public URL."""
    async with serving(
        engine,
        redis,
        settings=hermetic_settings(public_url=PUBLIC_URL, token_encryption_keys=[KEY]),
        base_url=PUBLIC_URL,
        bearer=bearer,
        follow_redirects=False,
        upstream_oidc_provider=provider or FakeProvider(),
    ) as (http, app):
        yield http, app


async def _seed(engine, *, identity_mode=IdentityMode.SHARED, with_client=True) -> McpServerRow:
    async with session_factory(engine)() as db:
        db.add(
            ApiKeyRow(
                name="svc",
                key_hash=hash_token(SERVICE_KEY),
                key_prefix=display_prefix(SERVICE_KEY),
                kind=ApiKeyKind.SERVICE,
            )
        )
        srv = McpServerRow(
            name="up",
            url="https://up/mcp",
            auth_mode=ServerAuthMode.UPSTREAM_OAUTH,
            identity_mode=identity_mode,
        )
        db.add(srv)
        await db.commit()
        await db.refresh(srv)
        if with_client:
            db.add(UpstreamOAuthClientRow(server_id=srv.id, client_id="cli"))
            await db.commit()
        return srv


@asynccontextmanager
async def _admin_session(engine, redis, provider=None):
    """The running gateway with a browser session for a freshly seeded admin."""
    async with session_factory(engine)() as db:
        admin = UserRow(oidc_issuer="i", oidc_sub="admin", email="a@x", is_admin=True)
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
    async with _running(engine, redis, provider=provider, bearer=SERVICE_KEY) as (http, app):
        sid = await app.state.container.admin_sessions.create(
            AdminSession(user_id=str(admin.id), email=admin.email, is_admin=True)
        )
        http.cookies.set(SESSION_COOKIE, sid)
        yield http, app, admin


async def test_connect_flow_stores_encrypted_token(engine, redis):
    await _seed(engine)
    async with _admin_session(engine, redis) as (http, app, admin):
        # start connect -> redirect to the upstream authorize
        resp = await http.get("/oauth/upstream/up/connect")
        assert resp.status_code == 302
        loc = resp.headers["location"]
        assert loc.startswith("https://idp/a?state=")
        state = loc.split("state=")[1].split("&")[0]

        # callback exchanges + stores (iss matches the recorded issuer)
        cb = await http.get(
            "/oauth/upstream/callback",
            params={"code": "xyz", "state": state, "iss": "https://idp"},
        )
        assert cb.status_code == 200
        assert "Connected" in cb.text

        # assert inside the lifespan — the app disposes the engine on exit
        async with session_factory(engine)() as db:
            row = (await db.execute(select(UpstreamOAuthTokenRow))).scalar_one()
        assert row.user_id is None  # shared connection
        assert REFRESH_TOKEN not in row.tokens_encrypted  # ciphertext, not plaintext
        assert row.account_hint == "me@x"


async def _connect_state(http, path="/oauth/upstream/up/connect") -> str:
    resp = await http.get(path)
    assert resp.status_code == 302, resp.text
    return resp.headers["location"].split("state=")[1].split("&")[0]


async def test_callback_validates_the_issuer(engine, redis):
    """UPS-32 (RFC 9207): a wrong or missing iss is refused before the code is redeemed."""
    await _seed(engine)
    async with _admin_session(engine, redis) as (http, app, admin):
        state = await _connect_state(http)
        wrong = await http.get(
            "/oauth/upstream/callback",
            params={"code": "xyz", "state": state, "iss": "https://evil"},
        )
        assert wrong.status_code == 400 and "issuer mismatch" in wrong.text

        state = await _connect_state(http)
        missing = await http.get("/oauth/upstream/callback", params={"code": "xyz", "state": state})
        assert missing.status_code == 400 and "iss" in missing.text

        state = await _connect_state(http)
        failed = await http.get(
            "/oauth/upstream/callback",
            params={"error": "access_denied", "state": state, "iss": "https://idp"},
        )
        assert failed.status_code == 400 and "access_denied" in failed.text

        async with session_factory(engine)() as db:
            assert (await db.execute(select(UpstreamOAuthTokenRow))).first() is None


async def test_connect_requires_admin_for_shared(engine, redis):
    await _seed(engine)
    async with session_factory(engine)() as db:
        u = UserRow(oidc_issuer="i", oidc_sub="u", email="u@x", is_admin=False)
        db.add(u)
        await db.commit()
        await db.refresh(u)
    async with _running(engine, redis) as (http, app):
        sid = await app.state.container.admin_sessions.create(
            AdminSession(user_id=str(u.id), email=u.email, is_admin=False)
        )
        http.cookies.set(SESSION_COOKIE, sid)
        resp = await http.get("/oauth/upstream/up/connect")
    assert resp.status_code == 403


class CountingProvider(FakeProvider):
    """The fake upstream, counting how often a code is redeemed."""

    def __init__(self) -> None:
        self.exchanges = 0

    async def exchange(self, meta, **kw):
        self.exchanges += 1
        return await super().exchange(meta, **kw)


async def _user(engine, sub: str, *, is_admin: bool = False) -> UserRow:
    async with session_factory(engine)() as db:
        user = UserRow(oidc_issuer="i", oidc_sub=sub, email=f"{sub}@x", is_admin=is_admin)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


async def _sign_in(http, app, user: UserRow) -> None:
    sid = await app.state.container.admin_sessions.create(
        AdminSession(user_id=str(user.id), email=user.email, is_admin=user.is_admin)
    )
    http.cookies.set(SESSION_COOKIE, sid)


async def _token_rows(engine) -> list:
    async with session_factory(engine)() as db:
        return list((await db.execute(select(UpstreamOAuthTokenRow))).scalars())


async def test_ups27_another_user_cannot_finish_per_user_connect(engine, redis):
    """UPS-27: a per-user connect handed to another signed-in user stores nothing for either."""
    await _seed(engine, identity_mode=IdentityMode.PER_USER)
    alice, bob = await _user(engine, "alice"), await _user(engine, "bob")
    provider = CountingProvider()
    async with _running(engine, redis, provider=provider) as (http, app):
        await _sign_in(http, app, alice)
        state = await _connect_state(http, "/oauth/upstream/up/connect?as=me")
        await _sign_in(http, app, bob)
        cb = await http.get(
            "/oauth/upstream/callback",
            params={"code": "xyz", "state": state, "iss": "https://idp"},
        )
        assert cb.status_code == 403 and "Connect not completed" in cb.text
        assert provider.exchanges == 0
        assert await _token_rows(engine) == []

        # the state is spent: the initiator cannot replay the link either
        await _sign_in(http, app, alice)
        replay = await http.get(
            "/oauth/upstream/callback",
            params={"code": "xyz", "state": state, "iss": "https://idp"},
        )
        assert replay.status_code == 400
        assert await _token_rows(engine) == []


async def test_ups27_callback_without_session_is_refused(engine, redis):
    """UPS-27: a callback in a browser without a gateway session is refused."""
    await _seed(engine, identity_mode=IdentityMode.PER_USER)
    alice = await _user(engine, "alice")
    provider = CountingProvider()
    async with _running(engine, redis, provider=provider) as (http, app):
        await _sign_in(http, app, alice)
        state = await _connect_state(http, "/oauth/upstream/up/connect?as=me")
        http.cookies.clear()
        cb = await http.get(
            "/oauth/upstream/callback",
            params={"code": "xyz", "state": state, "iss": "https://idp"},
        )
        assert cb.status_code == 403 and "start the connect again" in cb.text
        assert provider.exchanges == 0
        assert await _token_rows(engine) == []


async def test_ups27_non_admin_cannot_finish_shared_connect(engine, redis):
    """UPS-27: the shared connect started by an admin is not finished by a non-admin."""
    await _seed(engine)
    admin, user = await _user(engine, "admin", is_admin=True), await _user(engine, "user")
    provider = CountingProvider()
    async with _running(engine, redis, provider=provider) as (http, app):
        await _sign_in(http, app, admin)
        state = await _connect_state(http)
        await _sign_in(http, app, user)
        cb = await http.get(
            "/oauth/upstream/callback",
            params={"code": "xyz", "state": state, "iss": "https://idp"},
        )
        assert cb.status_code == 403
        assert provider.exchanges == 0
        assert await _token_rows(engine) == []


async def test_ups27_initiator_finishes_per_user_connect(engine, redis):
    """UPS-27: the user who started a per-user connect finishes it and owns the token."""
    await _seed(engine, identity_mode=IdentityMode.PER_USER)
    alice = await _user(engine, "alice")
    async with _running(engine, redis) as (http, app):
        await _sign_in(http, app, alice)
        state = await _connect_state(http, "/oauth/upstream/up/connect?as=me")
        cb = await http.get(
            "/oauth/upstream/callback",
            params={"code": "xyz", "state": state, "iss": "https://idp"},
        )
        assert cb.status_code == 200
        (row,) = await _token_rows(engine)
        assert row.user_id == alice.id


async def test_set_client_config_and_status(engine, redis):
    await _seed(engine, with_client=False)
    async with _running(engine, redis, bearer=SERVICE_KEY) as (http, _app):
        r = await http.put(
            "/api/v1/upstreams/up/upstream-oauth",
            json={"client_id": "cli", "client_secret": "shh"},
        )
        assert r.status_code == 200
        assert r.json()["has_secret"] is True

        status = await http.get("/api/v1/upstreams/up/upstream-oauth")
        body = status.json()
        assert body["shared"]["connected"] is False
        assert body["client_id"] == "cli"  # the UI prefills the registration form from this
        assert body["authorization_url"] is None and body["token_url"] is None
        assert "shh" not in json.dumps(body)  # no secret leak


async def test_ups30_endpoint_rejects_none_with_per_user_upstream(engine, redis):
    """UPS-30: a none-auth endpoint can't expose a per_user upstream bundle."""
    srv = await _seed(engine, identity_mode=IdentityMode.PER_USER)
    async with session_factory(engine)() as db:
        bundle = BundleRow(name="b")
        db.add(bundle)
        await db.commit()
        await db.refresh(bundle)
        db.add(BundleServerRow(bundle_id=bundle.id, server_id=srv.id))
        await db.commit()

    async with _running(engine, redis, bearer=SERVICE_KEY) as (http, _app):
        resp = await http.put(
            "/api/v1/endpoints/e",
            json={
                "name": "e",
                "bundle_name": "b",
                "auth_modes": ["none"],
                "allow_unauthenticated": True,
            },
        )
    assert resp.status_code == 409
    assert "UPS-30" in resp.json()["detail"]


async def test_ups30_allows_oauth_endpoint_with_per_user_upstream(engine, redis):
    srv = await _seed(engine, identity_mode=IdentityMode.PER_USER)
    async with session_factory(engine)() as db:
        bundle = BundleRow(name="b")
        db.add(bundle)
        await db.commit()
        await db.refresh(bundle)
        db.add(BundleServerRow(bundle_id=bundle.id, server_id=srv.id))
        await db.commit()

    async with _running(engine, redis, bearer=SERVICE_KEY) as (http, _app):
        resp = await http.put(
            "/api/v1/endpoints/e",
            json={
                "name": "e",
                "bundle_name": "b",
                "auth_modes": ["oauth"],
                "profile": "oauth_only",
            },
        )
    assert resp.status_code == 200


async def test_ups30_membership_rejects_per_user_upstream_behind_none_endpoint(engine, redis):
    """UPS-30: a per_user upstream can't join a bundle a none-auth endpoint already exposes."""
    await _seed(engine, identity_mode=IdentityMode.PER_USER)
    async with _running(engine, redis, bearer=SERVICE_KEY) as (http, _app):
        assert (await http.put("/api/v1/bundles/b", json={"name": "b"})).status_code == 200
        open_endpoint = await http.put(
            "/api/v1/endpoints/e",
            json={
                "name": "e",
                "bundle_name": "b",
                "auth_modes": ["none"],
                "allow_unauthenticated": True,
            },
        )
        assert open_endpoint.status_code == 200
        joined = await http.put("/api/v1/bundles/b/upstreams/up", json={"enabled": True})
    assert joined.status_code == 409
    assert "UPS-30" in joined.json()["detail"]


async def test_ups30_identity_switch_rejected_while_none_endpoint_exposes_server(engine, redis):
    """UPS-30: a member server can't switch to per_user under a none-auth endpoint."""
    await _seed(engine, identity_mode=IdentityMode.SHARED)
    async with _running(engine, redis, bearer=SERVICE_KEY) as (http, _app):
        assert (await http.put("/api/v1/bundles/b", json={"name": "b"})).status_code == 200
        assert (
            await http.put("/api/v1/bundles/b/upstreams/up", json={"enabled": True})
        ).status_code == 200
        assert (
            await http.put(
                "/api/v1/endpoints/e",
                json={
                    "name": "e",
                    "bundle_name": "b",
                    "auth_modes": ["none"],
                    "allow_unauthenticated": True,
                },
            )
        ).status_code == 200
        switched = await http.put(
            "/api/v1/upstreams/up",
            json={
                "name": "up",
                "url": "https://up/mcp",
                "auth_mode": "upstream_oauth",
                "identity_mode": "per_user",
            },
        )
        unchanged = await http.get("/api/v1/upstreams/up")
    assert switched.status_code == 409
    assert "UPS-30" in switched.json()["detail"]
    assert unchanged.json()["identity_mode"] == "shared"
