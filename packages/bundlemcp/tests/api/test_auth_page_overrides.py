"""Operator-branded auth pages (AUTH-38, AUTH-39, SEC-6): template overrides, assets, policy.

The page object is exercised directly where only rendering is in question; the
consent flow, the asset route and the startup check go through the composed app.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from bundlemcp.api.oauth.pages.auth_page import AuthPage
from bundlemcp.api.oauth.pages.auth_pages import auth_pages
from bundlemcp.api.oauth.pages.broken_auth_page import BrokenAuthPage
from bundlemcp.api.oauth.session_cookie import SESSION_COOKIE
from bundlemcp.domain.sessions.admin_session import AdminSession
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.bundle_row import BundleRow
from bundlemcp.infrastructure.postgres.rows.endpoint_row import EndpointRow
from bundlemcp.infrastructure.postgres.rows.user_row import UserRow
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI
from httpx import AsyncClient
from jinja2 import Environment, PackageLoader, select_autoescape
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.api.test_oauth import make_pkce
from tests.conftest import hermetic_settings, serving

PUBLIC_URL = "http://gw"
REDIRECT_URI = "https://client.example/cb"

SAME_ORIGIN_POLICY = (
    "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; form-action 'self'"
)
ASSETS_POLICY = (
    "default-src 'none'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self'; "
    "frame-ancestors 'none'; form-action 'self'"
)

# an override that changes every word and the markup, and keeps the form contract
BRANDED_CONSENT = """<!DOCTYPE html>
<html><head><link rel="stylesheet" href="{{ asset_url('brand/site.css') }}"></head>
<body><main class="branded">
  <img src="{{ asset_url('brand/logo.svg') }}" alt="">
  <h1>Let {{ client_name }} in?</h1>
  <p>{{ endpoint_name }} / {{ bundle_name }} / {{ scope }} for {{ user_email }}</p>
  <form method="post" action="{{ consent_action }}">
    <input type="hidden" name="token" value="{{ token }}">
    <button name="action" value="deny">Not now</button>
    <button name="action" value="approve">Let them in</button>
  </form>
</main></body></html>
"""


def _write(directory: Path, files: dict[str, str]) -> Path:
    for name, content in files.items():
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return directory


@pytest.fixture
def asset_dir(tmp_path: Path) -> Path:
    return _write(
        tmp_path / "assets",
        {
            "brand/logo.svg": "<svg xmlns='http://www.w3.org/2000/svg'/>",
            "brand/site.css": "main { color: teal }",
            "fonts/face.woff2": "wOF2",
            "page.html": "<p>not an asset</p>",
            "script.js": "alert(1)",
            ".hidden.css": "secret",
            "brand/.git/config.css": "secret",
        },
    )


@asynccontextmanager
async def _consenting_user(
    engine: AsyncEngine, redis: FakeRedis, **settings: object
) -> AsyncIterator[tuple[AsyncClient, FastAPI]]:
    """The app with one OAuth endpoint and a signed-in user, configured by ``settings``."""
    async with session_factory(engine)() as db:
        user = UserRow(oidc_issuer="http://idp", oidc_sub="alice", email="alice@example.com")
        bundle = BundleRow(name="b")
        db.add_all([user, bundle])
        await db.commit()
        await db.refresh(user)
        await db.refresh(bundle)
        db.add(EndpointRow(name="ep1", bundle_id=bundle.id, auth_modes=["oauth"]))
        await db.commit()
    async with serving(
        engine,
        redis,
        settings=hermetic_settings(public_url=PUBLIC_URL, **settings),
        base_url=PUBLIC_URL,
        follow_redirects=False,
    ) as (http, app):
        session_id = await app.state.container.admin_sessions.create(
            AdminSession(user_id=str(user.id), email=user.email, is_admin=False)
        )
        http.cookies.set(SESSION_COOKIE, session_id)
        yield http, app


async def _consent_page(http: AsyncClient, redirect_uri: str = REDIRECT_URI):
    registered = await http.post(
        "/oauth/register", json={"redirect_uris": [redirect_uri], "client_name": "<script>x"}
    )
    assert registered.status_code == 201, registered.text
    _, challenge = make_pkce()
    page = await http.get(
        "/oauth/authorize",
        params={
            "client_id": registered.json()["client_id"],
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


# -- rendering: overrides, fallback and the startup check


@pytest.mark.parametrize("page", list(AuthPage))
def test_auth38_default_rendering_is_the_built_in_template(page: AuthPage):
    """AUTH-38: without an override directory every page renders exactly as the plain
    package environment did, and its headers keep the same-origin policy."""
    plain = Environment(
        loader=PackageLoader("bundlemcp.api.oauth.pages", "templates"),
        autoescape=select_autoescape(["html"]),
    )
    pages = auth_pages(hermetic_settings())

    rendered = pages.render(page, **page.sample_values)

    assert rendered == plain.get_template(page.value).render(**page.sample_values)
    assert pages.headers() == {
        "Content-Security-Policy": SAME_ORIGIN_POLICY,
        "X-Frame-Options": "DENY",
        "Cache-Control": "no-store",
    }


def test_auth38_an_override_replaces_one_page_and_the_others_fall_back(tmp_path: Path):
    """AUTH-38: a file in the template directory replaces its page by name; pages without
    one keep the built-in template, and an override may extend a layout of its own."""
    _write(
        tmp_path,
        {
            "layout.html": "<body class='brand'>{% block body %}{% endblock %}</body>",
            "connected.html": (
                "{% extends 'layout.html' %}{% block body %}{{ server_name }} is in{% endblock %}"
            ),
        },
    )
    pages = auth_pages(hermetic_settings(auth_pages_template_dir=tmp_path))
    pages.verify()

    assert pages.render(AuthPage.CONNECTED, server_name="docs") == (
        "<body class='brand'>docs is in</body>"
    )
    refused = pages.render(AuthPage.CONNECT_REFUSED)
    assert "Connect not completed" in refused and "brand" not in refused


def test_auth38_override_values_stay_escaped(tmp_path: Path):
    """AUTH-38: autoescaping applies to an operator's template as to the built-in ones."""
    _write(tmp_path, {"connected.html": "<b>{{ server_name }}</b>"})
    pages = auth_pages(hermetic_settings(auth_pages_template_dir=tmp_path))

    assert pages.render(AuthPage.CONNECTED, server_name="<script>") == "<b>&lt;script&gt;</b>"


@pytest.mark.parametrize(
    "override, reason",
    [
        ("{% if %}", "TemplateSyntaxError"),
        ("<p>{{ client_nmae }}</p>", "client_nmae"),
        ("<img src=\"{{ asset_url('logo.svg') }}\">", "BUNDLEMCP_AUTH_PAGES_ASSET_DIR"),
    ],
    ids=["syntax", "unknown-variable", "asset-url-without-assets"],
)
async def test_auth38_a_broken_override_stops_the_start(
    engine: AsyncEngine, redis: FakeRedis, tmp_path: Path, override: str, reason: str
):
    """AUTH-38: every page is compiled and rendered at startup; a broken override stops the
    start with an error naming the file, before any request is served."""
    _write(tmp_path, {"consent.html": override})

    with pytest.raises(BrokenAuthPage) as raised:
        async with serving(
            engine, redis, settings=hermetic_settings(auth_pages_template_dir=tmp_path)
        ):
            pytest.fail("the app started with a broken consent.html")

    assert "consent.html" in str(raised.value)
    assert str(tmp_path / "consent.html") in str(raised.value)
    assert reason in str(raised.value)


@pytest.mark.parametrize("field", ["auth_pages_template_dir", "auth_pages_asset_dir"])
def test_auth38_a_setting_naming_no_directory_is_refused_at_load(tmp_path: Path, field: str):
    """AUTH-38, AUTH-39: a template or asset directory that does not exist, or is a file,
    refuses the settings."""
    a_file = _write(tmp_path, {"file.txt": "x"}) / "file.txt"
    for value in (tmp_path / "missing", a_file):
        with pytest.raises(ValidationError):
            hermetic_settings(**{field: value})


async def test_auth38_consent_approves_and_denies_with_an_overridden_template(
    engine: AsyncEngine, redis: FakeRedis, tmp_path: Path, asset_dir: Path
):
    """AUTH-38: an override that keeps the form contract still grants and refuses."""
    templates = _write(tmp_path / "templates", {"consent.html": BRANDED_CONSENT})
    async with _consenting_user(
        engine, redis, auth_pages_template_dir=templates, auth_pages_asset_dir=asset_dir
    ) as (http, _app):
        page, token = await _consent_page(http)
        assert "Let them in" in page.text and "Authorize access" not in page.text
        assert "Let &lt;script&gt;x in?" in page.text
        assert 'src="/auth-pages/assets/brand/logo.svg"' in page.text
        approved = await http.post("/oauth/consent", data={"token": token, "action": "approve"})

        _, token = await _consent_page(http)
        denied = await http.post("/oauth/consent", data={"token": token, "action": "deny"})

    assert approved.status_code == 302
    assert parse_qs(urlparse(approved.headers["location"]).query)["code"]
    assert denied.status_code == 302
    assert parse_qs(urlparse(denied.headers["location"]).query)["error"] == ["access_denied"]


async def test_auth38_controllers_pass_each_pages_contract(
    engine: AsyncEngine, redis: FakeRedis, tmp_path: Path
):
    """AUTH-38: the consent and return pages receive every variable their contract names;
    an override printing all of them renders through the real flow."""
    every_value = {
        page.value: " ".join(f"{name}=[{{{{ {name} }}}}]" for name in page.sample_values)
        for page in (AuthPage.CONSENT, AuthPage.RETURN_TO_CLIENT)
    }
    every_value["consent.html"] += "<form" + BRANDED_CONSENT.split("<form", 1)[1]
    templates = _write(tmp_path, every_value)
    async with _consenting_user(engine, redis, auth_pages_template_dir=templates) as (http, _):
        # a redirect URI that cannot be a CSP source is answered with the return page
        page, token = await _consent_page(http, "https://client.example/cb;v=1")
        answer = await http.post("/oauth/consent", data={"token": token, "action": "approve"})

    assert "endpoint_name=[ep1]" in page.text and "user_email=[alice@example.com]" in page.text
    assert "consent_action=[/oauth/consent]" in page.text
    assert answer.status_code == 200
    assert "heading=[Access granted]" in answer.text
    assert "location=[https://client.example/cb;v=1?" in answer.text


# -- assets: what the route serves and what it refuses


async def test_auth39_assets_are_served_with_type_and_cache_headers(
    engine: AsyncEngine, redis: FakeRedis, asset_dir: Path
):
    """AUTH-39: a file of a listed type is served read-only with its content type."""
    settings = hermetic_settings(auth_pages_asset_dir=asset_dir)
    async with serving(engine, redis, settings=settings) as (http, _app):
        logo = await http.get("/auth-pages/assets/brand/logo.svg")
        css = await http.get("/auth-pages/assets/brand/site.css")
        font = await http.get("/auth-pages/assets/fonts/face.woff2")

    assert logo.status_code == 200
    assert logo.headers["content-type"] == "image/svg+xml"
    assert logo.headers["cache-control"] == "public, max-age=3600"
    assert logo.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in logo.headers["content-security-policy"]
    assert logo.text == "<svg xmlns='http://www.w3.org/2000/svg'/>"
    assert css.headers["content-type"] == "text/css; charset=utf-8"
    assert font.headers["content-type"] == "font/woff2"


@pytest.mark.parametrize(
    "url",
    [
        "/auth-pages/assets/..%2Fsecret.css",
        "/auth-pages/assets/%2e%2e/secret.css",
        "/auth-pages/assets/brand/..%2F..%2Fsecret.css",
        "/auth-pages/assets//etc/secret.css",
        "/auth-pages/assets/escape.css",
        "/auth-pages/assets/brand",
        "/auth-pages/assets/brand/",
        "/auth-pages/assets/",
        "/auth-pages/assets/.hidden.css",
        "/auth-pages/assets/brand/.git/config.css",
        "/auth-pages/assets/page.html",
        "/auth-pages/assets/script.js",
        "/auth-pages/assets/missing.css",
    ],
)
async def test_auth39_traversal_listing_and_other_types_are_not_found(
    engine: AsyncEngine, redis: FakeRedis, tmp_path: Path, asset_dir: Path, url: str
):
    """AUTH-39: nothing outside the directory, no listing, no hidden files, no other types;
    a symbolic link pointing outside (escape.css) is refused too."""
    _write(tmp_path, {"secret.css": "outside", "etc/secret.css": "outside"})
    (asset_dir / "escape.css").symlink_to(tmp_path / "secret.css")
    settings = hermetic_settings(auth_pages_asset_dir=asset_dir)
    async with serving(engine, redis, settings=settings) as (http, _app):
        answer = await http.get(url)

    assert answer.status_code == 404
    assert "outside" not in answer.text


@pytest.mark.parametrize(
    "path",
    ["../secret.css", "brand/../../secret.css", "/etc/secret.css", "a\\..\\b.css", "x\x00.css"],
)
def test_auth39_lookup_refuses_paths_leaving_the_directory(
    tmp_path: Path, asset_dir: Path, path: str
):
    """AUTH-39: the lookup refuses traversal even where no client would send it."""
    _write(tmp_path, {"secret.css": "outside"})
    pages = auth_pages(hermetic_settings(auth_pages_asset_dir=asset_dir))

    assert pages.asset(path) is None
    assert pages.asset("brand/site.css") is not None


async def test_auth39_no_asset_route_without_the_setting(engine: AsyncEngine, redis: FakeRedis):
    """AUTH-39: unset, the route does not exist, and it never enters the OpenAPI document."""
    async with serving(engine, redis) as (http, app):
        answer = await http.get("/auth-pages/assets/logo.svg")

    assert answer.status_code == 404
    assert not any(getattr(r, "path", "").startswith("/auth-pages") for r in app.routes)


async def test_auth39_asset_route_is_not_published(
    engine: AsyncEngine, redis: FakeRedis, asset_dir: Path
):
    """AUTH-39: the asset route is served but kept out of the OpenAPI document."""
    settings = hermetic_settings(auth_pages_asset_dir=asset_dir)
    async with serving(engine, redis, settings=settings) as (_http, app):
        paths = app.openapi()["paths"]

    assert not any(path.startswith("/auth-pages") for path in paths)


# -- policy: the pages' Content-Security-Policy


async def test_sec6_consent_policy_admits_self_only_with_assets(
    engine: AsyncEngine, redis: FakeRedis, asset_dir: Path
):
    """SEC-6: with an asset directory the consent page admits same-origin styles, fonts and
    images, and keeps default-src, frame-ancestors and its form-action."""
    async with _consenting_user(engine, redis, auth_pages_asset_dir=asset_dir) as (http, _):
        page, _ = await _consent_page(http)

    assert page.headers["content-security-policy"] == f"{ASSETS_POLICY} {REDIRECT_URI}"
    assert page.headers["x-frame-options"] == "DENY"
    assert page.headers["cache-control"] == "no-store"


async def test_sec6_consent_policy_unchanged_without_assets(
    engine: AsyncEngine, redis: FakeRedis, tmp_path: Path
):
    """SEC-6: templates alone do not loosen the policy; only an asset directory does."""
    without_assets = "\n".join(
        line for line in BRANDED_CONSENT.splitlines() if "asset_url" not in line
    )
    templates = _write(tmp_path, {"consent.html": without_assets})
    async with _consenting_user(engine, redis, auth_pages_template_dir=templates) as (http, _):
        page, _ = await _consent_page(http)

    assert page.headers["content-security-policy"] == f"{SAME_ORIGIN_POLICY} {REDIRECT_URI}"


def test_sec6_other_pages_admit_self_only_with_assets(asset_dir: Path):
    """SEC-6: the pages that stay same-origin carry the asset directives only with assets."""
    with_assets = auth_pages(hermetic_settings(auth_pages_asset_dir=asset_dir)).headers()
    without = auth_pages(hermetic_settings()).headers()

    assert with_assets["Content-Security-Policy"] == ASSETS_POLICY
    assert without["Content-Security-Policy"] == SAME_ORIGIN_POLICY
