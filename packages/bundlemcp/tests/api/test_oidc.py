"""OIDC login + admin session + management-API session auth tests (the auth spec).

A fake OidcProvider stands in for Keycloak (ARC-14) — the login/callback,
provisioning, admin re-eval, cookie session, and CSRF machinery are what we test.
"""

from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlparse

import pytest
from bundlemcp.api.oauth.session_cookie import SESSION_COOKIE
from bundlemcp.domain.access.oidc_claims import OidcClaims
from bundlemcp.domain.access.oidc_unavailable import OidcUnavailable
from bundlemcp.domain.oauth.pkce import pkce_challenge
from bundlemcp.infrastructure.postgres.rows.user_row import UserRow
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select

from tests.conftest import hermetic_settings, serving

PUBLIC_URL = "http://gw"


class FakeOidcProvider:
    """Deterministic stand-in: authorize_url points back at our callback, and
    exchange returns preset claims keyed by the code.
    """

    def __init__(self) -> None:
        self.claims_by_code: dict[str, OidcClaims] = {}
        self.last_state: str | None = None
        self.last_nonce: str | None = None
        self.last_challenge: str | None = None
        self.last_verifier: str | None = None

    async def authorize_url(self, *, state, nonce, redirect_uri, code_challenge) -> str:
        self.last_state = state
        self.last_nonce = nonce
        self.last_challenge = code_challenge
        return f"{redirect_uri}?code=fake-code&state={state}"

    async def exchange(self, *, code, redirect_uri, nonce, code_verifier) -> OidcClaims:
        self.last_verifier = code_verifier
        return self.claims_by_code[code]


@pytest.fixture
async def env(engine: AsyncEngine, redis: FakeRedis) -> AsyncIterator[tuple]:
    settings = hermetic_settings(public_url=PUBLIC_URL, admin_emails=["admin@example.com"])
    provider = FakeOidcProvider()
    async with serving(
        engine,
        redis,
        settings=settings,
        base_url=PUBLIC_URL,
        follow_redirects=False,
        oidc_provider=provider,
    ) as (http, app):
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


async def test_login_proves_pkce_to_the_issuer(env):
    """AUTH-15: the exchange presents the verifier the authorize challenge commits to."""
    http, _, provider = env
    await _login(http, provider, OidcClaims(issuer="http://idp", sub="u1", email="u1@example.com"))
    assert provider.last_verifier is not None
    assert provider.last_challenge == pkce_challenge(provider.last_verifier)


async def test_login_provisions_user_and_sets_admin(env):
    """AUTH-16/AUTH-17: first login provisions; admin email -> is_admin."""
    http, app, provider = env
    await _login(
        http,
        provider,
        OidcClaims(
            issuer="http://idp",
            sub="admin1",
            email="admin@example.com",
            email_verified=True,
            name="Admin",
        ),
    )
    async with app.state.container.session_factory() as db:
        user = (await db.execute(select(UserRow))).scalar_one()
        assert user.email == "admin@example.com"
        assert user.is_admin is True
    assert http.cookies.get(SESSION_COOKIE)


async def test_admin_role_reevaluated_on_each_login(env):
    """AUTH-17: dropping the admin email demotes on next login."""
    http, app, provider = env
    await _login(
        http,
        provider,
        OidcClaims(issuer="http://idp", sub="u1", email="admin@example.com", email_verified=True),
    )
    async with app.state.container.session_factory() as db:
        assert (await db.execute(select(UserRow))).scalar_one().is_admin is True

    # same subject logs in, but is no longer an admin email match
    await _login(
        http, provider, OidcClaims(issuer="http://idp", sub="u1", email="user@example.com")
    )
    async with app.state.container.session_factory() as db:
        users = (await db.execute(select(UserRow))).scalars().all()
        assert len(users) == 1  # same (issuer, sub)
        assert users[0].is_admin is False


async def test_management_api_accepts_admin_session(env):
    """MGMT-2: admin cookie session authorizes management calls."""
    http, app, provider = env
    await _login(
        http,
        provider,
        OidcClaims(issuer="http://idp", sub="a", email="admin@example.com", email_verified=True),
    )
    resp = await http.get("/api/v1/upstreams")
    assert resp.status_code == 200


async def test_auth17_non_admin_session_answers_403(env):
    """AUTH-17: a signed-in user who is not an admin is known but forbidden: 403, not 401."""
    http, app, provider = env
    await _login(http, provider, OidcClaims(issuer="http://idp", sub="b", email="user@example.com"))
    resp = await http.get("/api/v1/upstreams")
    assert resp.status_code == 403
    assert (await http.get("/api/v1/me")).status_code == 200  # the catalogue still works


async def test_auth17_unverified_admin_email_answers_403(env):
    """AUTH-17: a listed admin email the issuer did not verify signs in as a plain user."""
    http, app, provider = env
    await _login(
        http, provider, OidcClaims(issuer="http://idp", sub="x", email="admin@example.com")
    )
    resp = await http.get("/api/v1/upstreams")
    assert resp.status_code == 403


async def test_auth17_no_session_is_still_401(env):
    """AUTH-17: a caller with no session or key at all gets 401."""
    http, _, _ = env
    assert (await http.get("/api/v1/upstreams")).status_code == 401


async def test_auth17_demotion_turns_an_admin_session_into_403(env):
    """AUTH-17: losing the admin email takes effect at the next login, as a 403."""
    http, app, provider = env
    await _login(
        http,
        provider,
        OidcClaims(issuer="http://idp", sub="a", email="admin@example.com", email_verified=True),
    )
    assert (await http.get("/api/v1/upstreams")).status_code == 200
    await _login(http, provider, OidcClaims(issuer="http://idp", sub="a", email="user@example.com"))
    assert (await http.get("/api/v1/upstreams")).status_code == 403


async def test_csrf_origin_check_on_mutation(env):
    """SEC-4: cookie-authenticated mutations need a same-origin Origin/Referer."""
    http, app, provider = env
    await _login(
        http,
        provider,
        OidcClaims(issuer="http://idp", sub="a", email="admin@example.com", email_verified=True),
    )
    body = {"name": "s1", "url": "http://s1/mcp"}

    # no Origin -> rejected
    bad = await http.put("/api/v1/upstreams/s1", json=body)
    assert bad.status_code == 403

    # cross-origin -> rejected
    cross = await http.put(
        "/api/v1/upstreams/s1", json=body, headers={"Origin": "http://evil.example"}
    )
    assert cross.status_code == 403

    # same-origin -> allowed
    ok = await http.put("/api/v1/upstreams/s1", json=body, headers={"Origin": PUBLIC_URL})
    assert ok.status_code == 200


async def test_logout_clears_session(env):
    http, app, provider = env
    await _login(
        http,
        provider,
        OidcClaims(issuer="http://idp", sub="a", email="admin@example.com", email_verified=True),
    )
    await http.post("/logout", headers={"Origin": PUBLIC_URL})
    resp = await http.get("/api/v1/upstreams")
    assert resp.status_code == 401


async def test_deactivation_logs_out_and_revokes(env):
    """AUTH-20: deactivating a user invalidates their admin session."""
    http, app, provider = env
    await _login(
        http,
        provider,
        OidcClaims(issuer="http://idp", sub="a", email="admin@example.com", email_verified=True),
    )
    async with app.state.container.session_factory() as db:
        user = (await db.execute(select(UserRow))).scalar_one()

    resp = await http.post(f"/api/v1/users/{user.id}:deactivate", headers={"Origin": PUBLIC_URL})
    assert resp.status_code == 200
    # session now fails is_active re-check
    follow = await http.get("/api/v1/upstreams")
    assert follow.status_code == 401


class UnreachableOidcProvider(FakeOidcProvider):
    """An IdP the gateway has not reached yet."""

    async def authorize_url(self, *, state, nonce, redirect_uri, code_challenge) -> str:
        raise OidcUnavailable("identity provider not reachable yet", retry_after=5)


async def test_login_while_idp_unreachable_answers_503_with_retry_after(engine, redis):
    """AUTH-21 (#86): no 'no provider configured' for the process's life; a 503 to retry."""
    settings = hermetic_settings(public_url=PUBLIC_URL)
    async with serving(
        engine,
        redis,
        settings=settings,
        base_url=PUBLIC_URL,
        follow_redirects=False,
        oidc_provider=UnreachableOidcProvider(),
    ) as (http, app):
        resp = await http.get("/login")
        assert resp.status_code == 503
        assert resp.headers["Retry-After"] == "5"
        # Readiness and the OAuth metadata do not depend on the IdP.
        assert (await http.get("/readyz")).status_code == 200
        assert (await http.get("/.well-known/oauth-authorization-server")).status_code == 200


async def _callback(http, provider, claims: OidcClaims):
    """Run the login flow and return the callback's response, whatever it is."""
    provider.claims_by_code["fake-code"] = claims
    location = (await http.get("/login", params={"next": "/"})).headers["location"]
    q = parse_qs(urlparse(location).query)
    return await http.get("/login/callback", params={"code": q["code"][0], "state": q["state"][0]})


async def test_auth20_relogin_does_not_reactivate(env):
    """AUTH-20: a deactivated user who signs in at the IdP again gets no session and stays off."""
    http, app, provider = env
    admin = OidcClaims(issuer="http://idp", sub="a", email="admin@example.com", email_verified=True)
    member = OidcClaims(issuer="http://idp", sub="m", email="member@example.com")
    await _login(http, provider, member)
    await _login(http, provider, admin)
    async with app.state.container.session_factory() as db:
        user = (await db.execute(select(UserRow).where(UserRow.oidc_sub == "m"))).scalar_one()
    await http.post(f"/api/v1/users/{user.id}:deactivate", headers={"Origin": PUBLIC_URL})

    http.cookies.clear()
    refused = await _callback(http, provider, member)
    assert refused.status_code == 403
    assert "deactivated" in refused.text
    assert "frame-ancestors 'none'" in refused.headers["content-security-policy"]
    assert SESSION_COOKIE not in refused.headers.get("set-cookie", "")
    async with app.state.container.session_factory() as db:
        assert (await db.get(UserRow, user.id)).is_active is False


async def test_auth20_reactivation_lets_the_user_sign_in_with_nothing_restored(env):
    """AUTH-20: :activate lets the user sign in again; consents and connections stay gone."""
    http, app, provider = env
    member = OidcClaims(issuer="http://idp", sub="m", email="member@example.com")
    await _login(http, provider, member)
    await _login(
        http,
        provider,
        OidcClaims(issuer="http://idp", sub="a", email="admin@example.com", email_verified=True),
    )
    async with app.state.container.session_factory() as db:
        user = (await db.execute(select(UserRow).where(UserRow.oidc_sub == "m"))).scalar_one()
    origin = {"Origin": PUBLIC_URL}
    await http.post(f"/api/v1/users/{user.id}:deactivate", headers=origin)
    reactivated = await http.post(f"/api/v1/users/{user.id}:activate", headers=origin)
    assert reactivated.status_code == 200
    assert reactivated.json()["is_active"] is True
    assert (await http.get(f"/api/v1/users/{user.id}/consents")).json() == []

    http.cookies.clear()
    assert (await _callback(http, provider, member)).status_code == 302


async def test_auth15_session_lifetime_follows_the_setting(engine, redis):
    """AUTH-15: the cookie's max age and the stored session's TTL are the configured lifetime."""
    settings = hermetic_settings(
        public_url="https://gw.example.com",
        admin_emails=["admin@example.com"],
        admin_session_lifetime=3600,
    )
    provider = FakeOidcProvider()
    async with serving(
        engine,
        redis,
        settings=settings,
        base_url="https://gw.example.com",
        follow_redirects=False,
        oidc_provider=provider,
    ) as (http, _app):
        provider.claims_by_code["fake-code"] = OidcClaims(
            issuer="http://idp", sub="a", email="admin@example.com", email_verified=True
        )
        location = (await http.get("/login", params={"next": "/"})).headers["location"]
        q = parse_qs(urlparse(location).query)
        callback = await http.get(
            "/login/callback", params={"code": q["code"][0], "state": q["state"][0]}
        )
    cookie = callback.headers["set-cookie"].lower()
    assert "max-age=3600" in cookie
    assert "httponly" in cookie and "samesite=lax" in cookie and "secure" in cookie
    assert "domain=" not in cookie  # host-only
    [key] = [k async for k in redis.scan_iter("bmcp:adminsession:*")]
    assert 3590 <= await redis.ttl(key) <= 3600


@pytest.mark.parametrize("seconds", [299, 2592001])
def test_auth15_out_of_range_lifetime_is_refused(seconds):
    """AUTH-15: a lifetime below five minutes or above thirty days fails settings validation."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="admin_session_lifetime"):
        hermetic_settings(admin_session_lifetime=seconds)


def _binding_set_cookies(resp) -> list[str]:
    return [c for c in resp.headers.get_list("set-cookie") if "bmcp_login" in c]


class _CountingStates:
    """Wraps the login state store to count `take` calls."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.takes = 0

    async def put(self, value):
        return await self.inner.put(value)

    async def take(self, token):
        self.takes += 1
        return await self.inner.take(token)


class _NoExchangeProvider(FakeOidcProvider):
    def __init__(self) -> None:
        super().__init__()
        self.exchanges = 0

    async def exchange(self, **kwargs) -> OidcClaims:
        self.exchanges += 1
        return await super().exchange(**kwargs)


async def test_auth15_callback_from_another_browser_is_refused(engine, redis):
    """AUTH-15: a callback link opened in a browser that never started the login is answered
    400 before the live store is touched, signs nobody in and never exchanges the code."""
    settings = hermetic_settings(public_url=PUBLIC_URL, admin_emails=["admin@example.com"])
    provider = _NoExchangeProvider()
    provider.claims_by_code["fake-code"] = OidcClaims(
        issuer="http://idp", sub="a", email="admin@example.com", email_verified=True
    )
    async with serving(
        engine,
        redis,
        settings=settings,
        base_url=PUBLIC_URL,
        follow_redirects=False,
        oidc_provider=provider,
    ) as (http, app):
        states = _CountingStates(app.state.container.oidc_login_states)
        app.state.container.oidc_login_states = states
        location = (await http.get("/login", params={"next": "/"})).headers["location"]
        q = parse_qs(urlparse(location).query)
        http.cookies.clear()  # the victim's browser holds no binding
        resp = await http.get(
            "/login/callback", params={"code": q["code"][0], "state": q["state"][0]}
        )
    assert resp.status_code == 400
    assert not any(SESSION_COOKIE in c for c in resp.headers.get_list("set-cookie"))
    assert provider.exchanges == 0
    assert states.takes == 0


async def test_auth15_mismatched_binding_is_refused(env):
    """AUTH-15: with two logins started in one browser, the first login's callback no longer
    matches the binding cookie and is refused."""
    http, _, provider = env
    provider.claims_by_code["fake-code"] = OidcClaims(
        issuer="http://idp", sub="a", email="admin@example.com", email_verified=True
    )
    first = parse_qs(urlparse((await http.get("/login")).headers["location"]).query)
    await http.get("/login")  # the second login replaces the binding cookie
    resp = await http.get(
        "/login/callback", params={"code": first["code"][0], "state": first["state"][0]}
    )
    assert resp.status_code == 400
    assert not any(SESSION_COOKIE in c for c in resp.headers.get_list("set-cookie"))
    assert http.cookies.get(SESSION_COOKIE) is None


async def test_auth15_https_binding_cookie_uses_host_prefix(engine, redis):
    """AUTH-15: on an https public URL the binding cookie is __Host- prefixed, Secure, HttpOnly,
    Lax, Path=/, host-only and lives 600 seconds; on plain http it is neither."""
    settings = hermetic_settings(public_url="https://gw.example.com")
    async with serving(
        engine,
        redis,
        settings=settings,
        base_url="https://gw.example.com",
        follow_redirects=False,
        oidc_provider=FakeOidcProvider(),
    ) as (http, _app):
        [cookie] = _binding_set_cookies(await http.get("/login"))
    lowered = cookie.lower()
    assert cookie.startswith("__Host-bmcp_login=")
    assert "; secure" in lowered and "; httponly" in lowered and "samesite=lax" in lowered
    assert "path=/" in lowered and "max-age=600" in lowered and "domain=" not in lowered


async def test_auth15_http_binding_cookie_has_no_host_prefix(env):
    """AUTH-15: on a plain-http public URL the binding cookie has no __Host- prefix and no
    Secure attribute."""
    http, _, _ = env
    [cookie] = _binding_set_cookies(await http.get("/login"))
    assert cookie.startswith("bmcp_login=")
    assert "; secure" not in cookie.lower()


async def test_auth15_callback_expires_binding_cookie(env):
    """AUTH-15: the callback expires the binding cookie when it signs the browser in and when it
    refuses it."""
    http, _, provider = env
    provider.claims_by_code["fake-code"] = OidcClaims(
        issuer="http://idp", sub="a", email="admin@example.com", email_verified=True
    )
    q = parse_qs(urlparse((await http.get("/login")).headers["location"]).query)
    ok = await http.get("/login/callback", params={"code": q["code"][0], "state": q["state"][0]})
    assert ok.status_code == 302
    [expired] = _binding_set_cookies(ok)
    assert "max-age=0" in expired.lower()

    refused = await http.get("/login/callback", params={"code": "x", "state": "bogus"})
    assert refused.status_code == 400
    [expired] = _binding_set_cookies(refused)
    assert "max-age=0" in expired.lower()
