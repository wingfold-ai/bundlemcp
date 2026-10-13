"""The identity provider is discovered once it is reachable, not only at startup (AUTH-21)."""

import asyncio

import httpx
import pytest
from bundlemcp.domain.access.oidc_unavailable import OidcUnavailable
from bundlemcp.infrastructure.oidc import discovering_oidc_provider
from bundlemcp.infrastructure.oidc.discovering_oidc_provider import (
    LOGIN_RETRY_FLOOR_SECONDS,
    DiscoveringOidcProvider,
)
from bundlemcp.infrastructure.oidc.jose_oidc_provider import JoseOidcProvider

from tests.infrastructure.test_oidc_provider import (
    CHALLENGE,
    ISSUER,
    REDIRECT_URI,
    VERIFIER,
    FakeIdp,
    _settings,
)


class FlakyIdp(FakeIdp):
    """A FakeIdp whose discovery document can be taken down, counting every fetch."""

    def __init__(self) -> None:
        super().__init__()
        self.up = False
        self.discovery_fetches = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            self.discovery_fetches += 1
            if not self.up:
                return httpx.Response(503)
        return super().handler(request)


class ManualClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _provider(idp: FlakyIdp, clock: ManualClock | None = None) -> DiscoveringOidcProvider:
    settings = _settings()
    return DiscoveringOidcProvider(
        lambda: JoseOidcProvider.discover(settings, client_factory=idp.client_factory()),
        clock=clock or ManualClock(),
    )


async def _authorize(provider: DiscoveringOidcProvider) -> str:
    return await provider.authorize_url(
        state="st", nonce="n0nce", redirect_uri=REDIRECT_URI, code_challenge=CHALLENGE
    )


async def test_login_discovers_an_idp_that_came_up_after_startup():
    """AUTH-21 (#86): a failed discovery is not kept; a later login retries and succeeds."""
    idp, clock = FlakyIdp(), ManualClock()
    provider = _provider(idp, clock)

    with pytest.raises(OidcUnavailable) as unavailable:
        await _authorize(provider)
    assert unavailable.value.retry_after == LOGIN_RETRY_FLOOR_SECONDS

    idp.up = True
    clock.now += LOGIN_RETRY_FLOOR_SECONDS
    assert (await _authorize(provider)).startswith(f"{ISSUER}/auth?")


async def test_logins_within_the_retry_floor_do_not_refetch():
    """AUTH-21: a burst of logins while the IdP is down costs one discovery fetch."""
    idp, clock = FlakyIdp(), ManualClock()
    provider = _provider(idp, clock)

    for _ in range(5):
        with pytest.raises(OidcUnavailable):
            await _authorize(provider)
        clock.now += 1
    assert idp.discovery_fetches == 1

    # The floor has passed; the next login tries again.
    with pytest.raises(OidcUnavailable):
        await _authorize(provider)
    assert idp.discovery_fetches == 2


async def test_failed_refresh_keeps_the_document_already_fetched():
    """AUTH-21: once discovered, an IdP outage does not undo it; the login still completes."""
    idp = FlakyIdp()
    idp.up = True
    idp.id_token = idp.sign()
    provider = _provider(idp)
    await provider.refresh()

    idp.up = False
    with pytest.raises(OidcUnavailable):
        await provider.refresh()
    assert (await _authorize(provider)).startswith(f"{ISSUER}/auth?")
    claims = await provider.exchange(
        code="c0de", redirect_uri=REDIRECT_URI, nonce="n0nce", code_verifier=VERIFIER
    )
    assert claims.sub == "alice"


async def test_background_loop_discovers_without_a_login(monkeypatch):
    """AUTH-21: the background retry picks the IdP up on its own once it answers."""
    monkeypatch.setattr(discovering_oidc_provider, "BACKOFF_INITIAL_SECONDS", 0.01)
    monkeypatch.setattr(discovering_oidc_provider, "BACKOFF_CAP_SECONDS", 0.02)
    idp = FlakyIdp()
    provider = _provider(idp)
    provider.start()
    try:
        while idp.discovery_fetches < 2:  # failed at least once, and retried
            await asyncio.sleep(0.01)
        idp.up = True
        async with asyncio.timeout(5):
            while True:
                try:
                    await _authorize(provider)
                    break
                except OidcUnavailable:
                    await asyncio.sleep(0.01)
    finally:
        provider.stop()
    fetches = idp.discovery_fetches
    await _authorize(provider)
    assert idp.discovery_fetches == fetches  # served from the document now held
