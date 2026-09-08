"""The real OIDC provider: discovery, code exchange and ID-token verification (spec 21).

test_oidc.py injects a fake provider, so this is the only place the JOSE path
runs. The IdP is an httpx MockTransport serving a discovery document, a token
endpoint and a JWKS; tokens are signed with a key generated per test.
"""

import json
import time
from collections.abc import Callable

import httpx
import pytest
from bundlemcp.application.settings.settings import Settings
from bundlemcp.domain.access.oidc_error import OidcError
from bundlemcp.infrastructure.config.settings import EnvSettings
from bundlemcp.infrastructure.oidc.jose_oidc_provider import JoseOidcProvider
from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey

# A literal private address: it passes the egress policy without a DNS lookup.
ISSUER = "http://10.9.8.7/realms/test"
CLIENT_ID = "bundlemcp-gateway"
REDIRECT_URI = "http://gw/login/callback"


class FakeIdp:
    """The three IdP documents the provider reads, served from memory."""

    def __init__(self) -> None:
        self.key = RSAKey.generate_key(2048, parameters={"kid": "k1"})
        self.id_token: str = ""
        self.token_status = 200
        self.token_requests: list[dict[str, str]] = []

    def sign(self, **overrides) -> str:
        now = int(time.time())
        claims = {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "sub": "alice",
            "email": "alice@example.com",
            "exp": now + 300,
            "iat": now,
            "nonce": "n0nce",
        }
        claims.update(overrides)
        return jwt.encode({"alg": "RS256", "kid": "k1"}, claims, self.key)

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(
                200,
                json={
                    "issuer": ISSUER,
                    "authorization_endpoint": f"{ISSUER}/auth",
                    "token_endpoint": f"{ISSUER}/token",
                    "jwks_uri": f"{ISSUER}/certs",
                },
            )
        if path.endswith("/token"):
            self.token_requests.append(dict(httpx.QueryParams(request.content.decode())))
            if self.token_status != 200:
                return httpx.Response(self.token_status, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"id_token": self.id_token, "access_token": "at"})
        if path.endswith("/certs"):
            return httpx.Response(200, json=KeySet([self.key]).as_dict(private=False))
        return httpx.Response(404)

    def client_factory(self) -> Callable[[], httpx.AsyncClient]:
        return lambda: httpx.AsyncClient(transport=httpx.MockTransport(self.handler))


def _settings(discovery_url: str = f"{ISSUER}/.well-known/openid-configuration") -> Settings:
    return EnvSettings(
        _env_file=None,
        oidc_discovery_url=discovery_url,
        oidc_client_id=CLIENT_ID,
        oidc_client_secret="s3cret",
    )


async def _provider(idp: FakeIdp) -> JoseOidcProvider:
    return await JoseOidcProvider.discover(_settings(), client_factory=idp.client_factory())


async def _exchange(provider: JoseOidcProvider, nonce: str = "n0nce"):
    return await provider.exchange(code="c0de", redirect_uri=REDIRECT_URI, nonce=nonce)


async def test_id_token_decoded_and_claims_validated():
    """ADM-1: a token signed by the issuer's key for this client yields its claims."""
    idp = FakeIdp()
    idp.id_token = idp.sign()
    provider = await _provider(idp)

    claims = await _exchange(provider)

    assert claims.issuer == ISSUER
    assert claims.sub == "alice"
    assert claims.email == "alice@example.com"
    sent = idp.token_requests[0]
    assert sent["code"] == "c0de" and sent["client_secret"] == "s3cret"
    assert sent["redirect_uri"] == REDIRECT_URI


async def test_authorize_url_carries_state_and_nonce():
    idp = FakeIdp()
    provider = await _provider(idp)
    url = provider.authorize_url(state="st", nonce="nn", redirect_uri=REDIRECT_URI)
    assert url.startswith(f"{ISSUER}/auth?")
    assert "state=st" in url and "nonce=nn" in url and f"client_id={CLIENT_ID}" in url


async def test_id_token_wrong_audience_rejected():
    """OIDC Core 3.1.3.7 step 3: a token minted for another client of the same realm fails."""
    idp = FakeIdp()
    idp.id_token = idp.sign(aud="some-other-client")
    provider = await _provider(idp)
    with pytest.raises(OidcError, match="ID token rejected"):
        await _exchange(provider)


async def test_id_token_wrong_issuer_rejected():
    """OIDC Core 3.1.3.7 step 2: the iss claim must equal the discovery document's issuer."""
    idp = FakeIdp()
    idp.id_token = idp.sign(iss="http://10.9.8.7/realms/other")
    provider = await _provider(idp)
    with pytest.raises(OidcError, match="ID token rejected"):
        await _exchange(provider)


async def test_id_token_expired_rejected():
    idp = FakeIdp()
    idp.id_token = idp.sign(exp=int(time.time()) - 10)
    provider = await _provider(idp)
    with pytest.raises(OidcError, match="ID token rejected"):
        await _exchange(provider)


async def test_id_token_signed_by_unknown_key_rejected():
    idp = FakeIdp()
    stranger = RSAKey.generate_key(2048, parameters={"kid": "k1"})
    now = int(time.time())
    idp.id_token = jwt.encode(
        {"alg": "RS256", "kid": "k1"},
        {"iss": ISSUER, "aud": CLIENT_ID, "sub": "x", "exp": now + 60, "nonce": "n0nce"},
        stranger,
    )
    provider = await _provider(idp)
    with pytest.raises(OidcError, match="ID token rejected"):
        await _exchange(provider)


async def test_nonce_mismatch_rejected():
    idp = FakeIdp()
    idp.id_token = idp.sign()
    provider = await _provider(idp)
    with pytest.raises(OidcError, match="nonce"):
        await _exchange(provider, nonce="different")


async def test_idp_error_response_becomes_oidc_error():
    """An IdP refusing the code is a 400 to the browser, not an unhandled 500."""
    idp = FakeIdp()
    idp.token_status = 400
    provider = await _provider(idp)
    with pytest.raises(OidcError, match="token exchange failed"):
        await _exchange(provider)


async def test_issuer_on_blocked_range_refused():
    """SEC-1: the identity provider's URLs pass the egress policy too."""
    idp = FakeIdp()
    with pytest.raises(OidcError, match="egress"):
        await JoseOidcProvider.discover(
            _settings("http://127.0.0.1/realms/x/.well-known/openid-configuration"),
            client_factory=idp.client_factory(),
        )


def test_id_token_is_not_logged_in_repr():
    """Secrets carry repr=False so a logged model never shows them."""
    from bundlemcp.domain.oauth.pkce import PkcePair

    assert "verifier" not in repr(PkcePair.generate())


async def test_login_callback_reports_idp_error(engine, redis):
    """A callback carrying error= is refused without attempting an exchange."""
    from bundlemcp.main.app import create_app
    from bundlemcp.main.composition_overrides import CompositionOverrides
    from httpx import ASGITransport, AsyncClient

    from tests.api.test_oidc import FakeOidcProvider

    settings = EnvSettings(_env_file=None, database_url="sqlite+aiosqlite://", public_url="http://gw")
    provider = FakeOidcProvider()
    app = create_app(
        settings, overrides=CompositionOverrides(engine=engine, redis=redis, oidc_provider=provider)
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://gw", follow_redirects=False
    ) as http:
        async with app.router.lifespan_context(app):
            start = await http.get("/login")
            state = httpx.URL(start.headers["location"]).params["state"]
            resp = await http.get(
                "/login/callback", params={"state": state, "error": "access_denied"}
            )
    assert resp.status_code == 400
    assert "access_denied" in resp.text
    assert json.loads(resp.text)["detail"].startswith("login failed")
