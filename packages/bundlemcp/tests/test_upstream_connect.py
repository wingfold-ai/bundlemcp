"""Upstream OAuth connect flow + management + UPO-6 tests (spec 23)."""

import json

from bundlemcp.api.app import create_app
from bundlemcp.api.composition_overrides import CompositionOverrides
from bundlemcp.crypto import API_KEY_PREFIX, display_prefix, generate_token, hash_token
from bundlemcp.models import (
    ApiKey,
    ApiKeyKind,
    Bundle,
    BundleServer,
    IdentityMode,
    McpServer,
    ServerAuthMode,
    UpstreamOAuthClient,
    UpstreamOAuthToken,
    User,
)
from bundlemcp.oauth.session_cookie import SESSION_COOKIE
from bundlemcp.oauth.upstream_client import UpstreamMetadata, UpstreamTokens
from bundlemcp.settings import Settings
from bundlemcp.store import session_factory
from bundlemcp.store.admin_sessions import AdminSession
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

KEY = Fernet.generate_key().decode()
SERVICE_KEY = generate_token(API_KEY_PREFIX)
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


def _settings():
    return Settings(
        _env_file=None,
        database_url="sqlite+aiosqlite://",
        public_url=PUBLIC_URL,
        token_encryption_keys=[KEY],
    )


def _make_app(engine, redis, provider=None):
    return create_app(
        _settings(),
        overrides=CompositionOverrides(
            engine=engine, redis=redis, upstream_oidc_provider=provider or FakeProvider()
        ),
    )


async def _seed(engine, *, identity_mode=IdentityMode.SHARED, with_client=True) -> McpServer:
    async with session_factory(engine)() as db:
        db.add(
            ApiKey(
                name="svc",
                key_hash=hash_token(SERVICE_KEY),
                key_prefix=display_prefix(SERVICE_KEY),
                kind=ApiKeyKind.SERVICE,
            )
        )
        srv = McpServer(
            name="up",
            url="https://up/mcp",
            auth_mode=ServerAuthMode.UPSTREAM_OAUTH,
            identity_mode=identity_mode,
        )
        db.add(srv)
        await db.commit()
        await db.refresh(srv)
        if with_client:
            db.add(UpstreamOAuthClient(server_id=srv.id, client_id="cli"))
            await db.commit()
        return srv


async def _admin_client(engine, redis, provider=None):
    app = _make_app(engine, redis, provider)
    async with session_factory(engine)() as db:
        admin = User(oidc_issuer="i", oidc_sub="admin", email="a@x", is_admin=True)
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
    http = AsyncClient(
        transport=ASGITransport(app=app),
        base_url=PUBLIC_URL,
        headers={"Authorization": f"Bearer {SERVICE_KEY}"},
        follow_redirects=False,
    )
    return app, http, admin


async def test_connect_flow_stores_encrypted_token(engine, redis):
    await _seed(engine)
    app, http, admin = await _admin_client(engine, redis)
    async with http:
        async with app.router.lifespan_context(app):
            sid = await app.state.container.admin_sessions.create(
                AdminSession(user_id=str(admin.id), email=admin.email, is_admin=True)
            )
            http.cookies.set(SESSION_COOKIE, sid)

            # start connect -> redirect to the upstream authorize
            resp = await http.get("/oauth/upstream/up/connect")
            assert resp.status_code == 302
            loc = resp.headers["location"]
            assert loc.startswith("https://idp/a?state=")
            state = loc.split("state=")[1].split("&")[0]

            # callback exchanges + stores (UPO-8: iss matches the recorded issuer)
            cb = await http.get(
                "/oauth/upstream/callback",
                params={"code": "xyz", "state": state, "iss": "https://idp"},
            )
            assert cb.status_code == 200
            assert "Connected" in cb.text

            # assert inside the lifespan — the app disposes the engine on exit
            from sqlmodel import select

            async with session_factory(engine)() as db:
                row = (await db.execute(select(UpstreamOAuthToken))).scalar_one()
            assert row.user_id is None  # shared connection
            assert REFRESH_TOKEN not in row.tokens_encrypted  # ciphertext, not plaintext
            assert row.account_hint == "me@x"


async def _connect_state(http, path="/oauth/upstream/up/connect") -> str:
    resp = await http.get(path)
    assert resp.status_code == 302, resp.text
    return resp.headers["location"].split("state=")[1].split("&")[0]


async def test_callback_validates_the_issuer(engine, redis):
    """UPO-8 (RFC 9207): a wrong or missing iss is refused before the code is redeemed."""
    await _seed(engine)
    app, http, admin = await _admin_client(engine, redis)
    async with http:
        async with app.router.lifespan_context(app):
            sid = await app.state.container.admin_sessions.create(
                AdminSession(user_id=str(admin.id), email=admin.email, is_admin=True)
            )
            http.cookies.set(SESSION_COOKIE, sid)

            state = await _connect_state(http)
            wrong = await http.get(
                "/oauth/upstream/callback",
                params={"code": "xyz", "state": state, "iss": "https://evil"},
            )
            assert wrong.status_code == 400 and "issuer mismatch" in wrong.text

            state = await _connect_state(http)
            missing = await http.get(
                "/oauth/upstream/callback", params={"code": "xyz", "state": state}
            )
            assert missing.status_code == 400 and "iss" in missing.text

            state = await _connect_state(http)
            failed = await http.get(
                "/oauth/upstream/callback",
                params={"error": "access_denied", "state": state, "iss": "https://idp"},
            )
            assert failed.status_code == 400 and "access_denied" in failed.text

            from sqlmodel import select

            async with session_factory(engine)() as db:
                assert (await db.execute(select(UpstreamOAuthToken))).first() is None


async def test_connect_requires_admin_for_shared(engine, redis):
    await _seed(engine)
    app = _make_app(engine, redis)
    async with session_factory(engine)() as db:
        u = User(oidc_issuer="i", oidc_sub="u", email="u@x", is_admin=False)
        db.add(u)
        await db.commit()
        await db.refresh(u)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=PUBLIC_URL, follow_redirects=False
    ) as http:
        async with app.router.lifespan_context(app):
            sid = await app.state.container.admin_sessions.create(
                AdminSession(user_id=str(u.id), email=u.email, is_admin=False)
            )
            http.cookies.set(SESSION_COOKIE, sid)
            resp = await http.get("/oauth/upstream/up/connect")
    assert resp.status_code == 403


async def test_set_client_config_and_status(engine, redis):
    await _seed(engine, with_client=False)
    app = _make_app(engine, redis)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url=PUBLIC_URL,
        headers={"Authorization": f"Bearer {SERVICE_KEY}"},
    ) as http:
        async with app.router.lifespan_context(app):
            r = await http.put(
                "/api/v1/servers/up/upstream-oauth",
                json={"client_id": "cli", "client_secret": "shh"},
            )
            assert r.status_code == 200
            assert r.json()["has_secret"] is True

            status = await http.get("/api/v1/servers/up/upstream-oauth")
            body = status.json()
            assert body["shared"]["connected"] is False
            assert "shh" not in json.dumps(body)  # no secret leak


async def test_upo6_endpoint_rejects_none_with_per_user_upstream(engine, redis):
    """UPO-6: a none-auth endpoint can't expose a per_user upstream bundle."""
    srv = await _seed(engine, identity_mode=IdentityMode.PER_USER)
    async with session_factory(engine)() as db:
        bundle = Bundle(name="b")
        db.add(bundle)
        await db.commit()
        await db.refresh(bundle)
        db.add(BundleServer(bundle_id=bundle.id, server_id=srv.id))
        await db.commit()

    app = _make_app(engine, redis)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url=PUBLIC_URL,
        headers={"Authorization": f"Bearer {SERVICE_KEY}"},
    ) as http:
        async with app.router.lifespan_context(app):
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
    assert "UPO-6" in resp.json()["detail"]


async def test_upo6_allows_oauth_endpoint_with_per_user_upstream(engine, redis):
    srv = await _seed(engine, identity_mode=IdentityMode.PER_USER)
    async with session_factory(engine)() as db:
        bundle = Bundle(name="b")
        db.add(bundle)
        await db.commit()
        await db.refresh(bundle)
        db.add(BundleServer(bundle_id=bundle.id, server_id=srv.id))
        await db.commit()

    app = _make_app(engine, redis)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url=PUBLIC_URL,
        headers={"Authorization": f"Bearer {SERVICE_KEY}"},
    ) as http:
        async with app.router.lifespan_context(app):
            resp = await http.put(
                "/api/v1/endpoints/e",
                json={
                    "name": "e",
                    "bundle_name": "b",
                    "auth_modes": ["oauth"],
                    "profile": "claude",
                },
            )
    assert resp.status_code == 200


async def test_upo6_membership_rejects_per_user_upstream_behind_none_endpoint(engine, redis):
    """UPO-6: a per_user upstream can't join a bundle a none-auth endpoint already exposes."""
    await _seed(engine, identity_mode=IdentityMode.PER_USER)
    app = _make_app(engine, redis)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url=PUBLIC_URL,
        headers={"Authorization": f"Bearer {SERVICE_KEY}"},
    ) as http:
        async with app.router.lifespan_context(app):
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
            joined = await http.put("/api/v1/bundles/b/servers/up", json={"enabled": True})
    assert joined.status_code == 409
    assert "UPO-6" in joined.json()["detail"]


async def test_upo6_identity_switch_rejected_while_none_endpoint_exposes_server(engine, redis):
    """UPO-6: a member server can't switch to per_user under a none-auth endpoint."""
    await _seed(engine, identity_mode=IdentityMode.SHARED)
    app = _make_app(engine, redis)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url=PUBLIC_URL,
        headers={"Authorization": f"Bearer {SERVICE_KEY}"},
    ) as http:
        async with app.router.lifespan_context(app):
            assert (await http.put("/api/v1/bundles/b", json={"name": "b"})).status_code == 200
            assert (
                await http.put("/api/v1/bundles/b/servers/up", json={"enabled": True})
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
                "/api/v1/servers/up",
                json={
                    "name": "up",
                    "url": "https://up/mcp",
                    "auth_mode": "upstream_oauth",
                    "identity_mode": "per_user",
                },
            )
            unchanged = await http.get("/api/v1/servers/up")
    assert switched.status_code == 409
    assert "UPO-6" in switched.json()["detail"]
    assert unchanged.json()["identity_mode"] == "shared"
