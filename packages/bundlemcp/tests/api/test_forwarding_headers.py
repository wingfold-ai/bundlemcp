"""Forwarding headers: only the gateway's trusted-proxy policy reads them (DEP-2)."""

import importlib.util
import pathlib

import uvicorn
from bundlemcp.main.app import create_app
from bundlemcp.main.composition_root import CompositionOverrides
from httpx import ASGITransport, AsyncClient

from tests.conftest import hermetic_settings

ROOT = pathlib.Path(__file__).resolve().parents[4]
PUBLIC_URL = "https://gw.example.com"


def gateway_server_config() -> uvicorn.Config:
    spec = importlib.util.spec_from_file_location("gateway_main", ROOT / "apps/gateway/main.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.server_config()


async def test_dep2_uvicorn_does_not_rewrite_the_peer_from_xff():
    """DEP-2: the container's server leaves X-Forwarded-For to the gateway, even from 127.0.0.1."""
    seen: list[tuple[str, int] | None] = []

    async def probe(scope, receive, send):
        seen.append(scope["client"])
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    served = gateway_server_config()
    config = uvicorn.Config(
        probe,
        proxy_headers=served.proxy_headers,
        forwarded_allow_ips=served.forwarded_allow_ips,
        log_config=None,
    )
    config.load()
    transport = ASGITransport(app=config.loaded_app, client=("127.0.0.1", 5000))
    async with AsyncClient(transport=transport, base_url="http://gw") as http:
        await http.get("/", headers={"X-Forwarded-For": "6.6.6.6"})
    assert served.proxy_headers is False
    assert seen == [("127.0.0.1", 5000)]


async def test_dep2_forwarded_scheme_and_host_do_not_change_published_urls(engine, redis):
    """DEP-2: forwarded scheme and host from a trusted proxy keep metadata on the public URL."""
    settings = hermetic_settings(public_url=PUBLIC_URL, trusted_proxies=["172.16.0.0/12"])
    app = create_app(settings, overrides=CompositionOverrides(engine=engine, redis=redis))
    transport = ASGITransport(app=app, client=("172.18.0.2", 5000))
    forged = {"X-Forwarded-Proto": "http", "X-Forwarded-Host": "evil.example"}
    async with AsyncClient(transport=transport, base_url="http://internal:8000") as http:
        async with app.router.lifespan_context(app):
            meta = (
                await http.get("/.well-known/oauth-authorization-server", headers=forged)
            ).json()
    assert meta["issuer"] == PUBLIC_URL
    assert all(
        value.startswith(PUBLIC_URL)
        for key, value in meta.items()
        if key.endswith("_endpoint") and isinstance(value, str)
    )
