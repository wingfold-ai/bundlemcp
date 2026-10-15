"""The endpoint catalogue for signed-in people (MGMT-1 `me/endpoints`, UI-2)."""

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


async def _login(http, provider, *, sub: str, email: str) -> None:
    provider.claims_by_code["fake-code"] = OidcClaims(issuer="http://idp", sub=sub, email=email)
    resp = await http.get("/login", params={"next": "/"})
    q = parse_qs(urlparse(resp.headers["location"]).query)
    await http.get("/login/callback", params={"code": q["code"][0], "state": q["state"][0]})


async def test_catalogue_lists_enabled_oauth_endpoints_for_non_admins(env):
    """A non-admin sees every enabled OAuth endpoint with its URL, nothing else."""
    http, provider = env
    web = {"Origin": WEB_ORIGIN}
    await _login(http, provider, sub="a", email="admin@example.com")
    created = await http.put(
        "/api/v1/bundles/b1",
        json={"name": "b1", "description": "Tools", "overview": "Everything about b1."},
        headers=web,
    )
    assert created.status_code == 200, created.text
    for name, body in {
        "connectors": {"profile": "oauth_only", "auth_modes": ["oauth"]},
        "scripts": {"profile": "default", "auth_modes": ["api_key"]},
        "paused": {"profile": "default", "auth_modes": ["oauth"], "enabled": False},
    }.items():
        resp = await http.put(
            f"/api/v1/endpoints/{name}",
            json={"name": name, "bundle_name": "b1", **body},
            headers=web,
        )
        assert resp.status_code == 200, resp.text

    await _login(http, provider, sub="u2", email="user@example.com")
    denied = await http.get("/api/v1/endpoints")
    assert denied.status_code == 403  # signed in, but not an admin

    catalogue = await http.get("/api/v1/me/endpoints")
    assert catalogue.status_code == 200
    assert catalogue.json() == [
        {
            "name": "connectors",
            "url": f"{PUBLIC_URL}/connectors/mcp",
            "profile": "oauth_only",
            "bundle_name": "b1",
            "bundle_description": "Tools",
            "bundle_overview": "Everything about b1.",
        }
    ]


async def test_catalogue_requires_a_signed_in_caller(env):
    http, _provider = env
    assert (await http.get("/api/v1/me/endpoints")).status_code == 401


async def test_catalogue_tools_are_refused_for_a_bundle_with_no_oauth_endpoint(env):
    """BND-11: a bundle nobody can connect to is not readable, and is not distinguished
    from one that does not exist."""
    http, provider = env
    web = {"Origin": WEB_ORIGIN}
    await _login(http, provider, sub="a", email="admin@example.com")
    for name in ("keyed", "open"):
        assert (
            await http.put(f"/api/v1/bundles/{name}", json={"name": name}, headers=web)
        ).status_code == 200
    assert (
        await http.put(
            "/api/v1/endpoints/keyed-ep",
            json={"name": "keyed-ep", "bundle_name": "keyed", "auth_modes": ["api_key"]},
            headers=web,
        )
    ).status_code == 200
    assert (
        await http.put(
            "/api/v1/endpoints/open-ep",
            json={"name": "open-ep", "bundle_name": "open", "auth_modes": ["oauth"]},
            headers=web,
        )
    ).status_code == 200

    await _login(http, provider, sub="u2", email="user@example.com")
    # reachable over OAuth: readable, and empty because the bundle has no members
    reachable = await http.get("/api/v1/me/bundles/open/tools")
    assert reachable.status_code == 200
    assert reachable.json() == []
    # api_key only, and unknown, are both "not found": neither reveals the bundle
    assert (await http.get("/api/v1/me/bundles/keyed/tools")).status_code == 404
    assert (await http.get("/api/v1/me/bundles/nope/tools")).status_code == 404


async def test_catalogue_tools_require_a_signed_in_caller(env):
    http, _provider = env
    assert (await http.get("/api/v1/me/bundles/b1/tools")).status_code == 401


async def test_catalogue_lists_the_bundles_own_prompts_and_resources(env):
    """BND-36: a signed-in person sees what context a bundle offers before connecting it,
    and only for a bundle they could connect to."""
    http, provider = env
    web = {"Origin": WEB_ORIGIN}
    await _login(http, provider, sub="a", email="admin@example.com")
    for name in ("keyed", "open"):
        await http.put(f"/api/v1/bundles/{name}", json={"name": name}, headers=web)
        await http.put(
            f"/api/v1/bundles/{name}/resources/guides/style",
            json={"name": "guides/style", "title": "House style", "content": "Use blue."},
            headers=web,
        )
        await http.put(
            f"/api/v1/bundles/{name}/prompts/plot",
            json={
                "name": "plot",
                "description": "Plot a series",
                "messages": [{"role": "user", "text": "Plot it"}],
            },
            headers=web,
        )
    await http.put(
        "/api/v1/endpoints/keyed-ep",
        json={"name": "keyed-ep", "bundle_name": "keyed", "auth_modes": ["api_key"]},
        headers=web,
    )
    await http.put(
        "/api/v1/endpoints/open-ep",
        json={"name": "open-ep", "bundle_name": "open", "auth_modes": ["oauth"]},
        headers=web,
    )

    await _login(http, provider, sub="u2", email="user@example.com")
    prompts = await http.get("/api/v1/me/bundles/open/prompts")
    resources = await http.get("/api/v1/me/bundles/open/resources")
    assert prompts.json() == [{"name": "plot", "title": None, "description": "Plot a series"}]
    assert resources.json() == [
        {"name": "guides/style", "title": "House style", "description": None}
    ]
    for kind in ("prompts", "resources"):
        assert (await http.get(f"/api/v1/me/bundles/keyed/{kind}")).status_code == 404
