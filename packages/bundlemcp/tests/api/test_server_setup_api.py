"""Guided server setup and upstream credentials through the ASGI app.

Spec 10 (SRV-11, SRV-12, SRV-14, SRV-15), spec 20 (OAS-5), spec 23 (UPO-1, UPO-4, UPO-10),
spec 24 (FWD-6, FWD-7).
"""

import json

from bundlemcp.application.upstream_oauth.upstream_token_service import UpstreamTokenService
from bundlemcp.domain.access.api_key_kind import ApiKeyKind
from bundlemcp.domain.servers.observed_response import ObservedResponse
from bundlemcp.domain.servers.server_auth_mode import ServerAuthMode
from bundlemcp.domain.upstream_oauth.needs_connect import NeedsConnect
from bundlemcp.domain.upstream_oauth.upstream_challenge import UpstreamChallenge
from bundlemcp.domain.upstream_oauth.upstream_tokens import UpstreamTokens
from bundlemcp.infrastructure.config.settings import EnvSettings
from bundlemcp.infrastructure.crypto.token_cipher import token_cipher
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.bundle_row import BundleRow
from bundlemcp.infrastructure.postgres.rows.bundle_server_row import BundleServerRow
from bundlemcp.infrastructure.postgres.rows.endpoint_row import EndpointRow
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.postgres.rows.tool_row import ToolRow
from bundlemcp.infrastructure.postgres.rows.upstream_oauth_client_row import (
    UpstreamOAuthClientRow,
)
from bundlemcp.infrastructure.postgres.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWorkFactory
from bundlemcp.infrastructure.valkey.refresh_lock import ValkeyRefreshLock
from cryptography.fernet import Fernet
from fastmcp import Client, FastMCP
from sqlmodel import select

from tests.conftest import ENDPOINT_KEY, SERVICE_KEY, hermetic_settings, seed_api_key, serving

KEY = Fernet.generate_key().decode()
weather = FastMCP("Weather Service", instructions="Forecasts")


@weather.tool
def forecast(city: str) -> str:
    """Tomorrow's forecast."""
    return f"sunny in {city}"


class RecordingFactory:
    """In-process upstream; remembers headers; can answer like a refusing HTTP server."""

    def __init__(self, refuse: ObservedResponse | None = None) -> None:
        self.headers: list[dict[str, str]] = []
        self.refuse = refuse

    def __call__(self, server, extra_headers, *, observer=None, **handlers):
        self.headers.append(dict(extra_headers))
        if self.refuse is not None:
            if observer is not None:
                observer.record(self.refuse)
            return _Failing()
        return Client(weather, **handlers)


class _Failing:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def call_tool_mcp(self, name, arguments, progress_handler=None, meta=None):
        raise RuntimeError("Server returned an error response")


async def _seed_delegated(engine, auth_mode=ServerAuthMode.DELEGATED_TOKEN):
    async with session_factory(engine)() as db:
        server = McpServerRow(name="weather", url="http://weather:8000/mcp", auth_mode=auth_mode)
        bundle = BundleRow(name="main")
        db.add_all([server, bundle])
        await db.commit()
        await db.refresh(server)
        await db.refresh(bundle)
        db.add_all(
            [
                BundleServerRow(bundle_id=bundle.id, server_id=server.id),
                EndpointRow(name="main", bundle_id=bundle.id, auth_modes=["api_key"]),
                ToolRow(server_id=server.id, name="forecast", schema_hash="h", input_schema={}),
            ]
        )
        await db.commit()


async def _call_forecast(http):
    return await http.post(
        "/main/mcp",
        headers={
            "Authorization": f"Bearer {ENDPOINT_KEY}",
            "MCP-Protocol-Version": "2026-07-28",
            "Mcp-Method": "tools/call",
            "Mcp-Name": "weather__forecast",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "weather__forecast",
                "arguments": {"city": "Bern"},
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                    "io.modelcontextprotocol/clientCapabilities": {},
                    "io.modelcontextprotocol/clientInfo": {"name": "t", "version": "1"},
                },
            },
        },
        timeout=30,
    )


def _result_of(response) -> dict:
    """The JSON-RPC message, whether it came as JSON or as the last SSE event."""
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        data = [
            line.removeprefix("data:").strip()
            for line in response.text.splitlines()
            if line.startswith("data:")
        ]
        return json.loads(data[-1])
    return response.json()


async def test_srv11_inspect_reports_a_ready_server(engine, redis):
    await seed_api_key(engine, SERVICE_KEY)
    async with serving(engine, redis, bearer=SERVICE_KEY, client_factory=RecordingFactory()) as (
        http,
        _,
    ):
        resp = await http.post("/api/v1/upstreams:inspect", json={"url": "http://weather:8000/mcp"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["connection_state"] == "ready"
    assert body["tool_names"] == ["forecast"]
    assert body["server_info"]["name"] == "Weather Service"
    assert body["suggestion"]["name"] == "weather-service"
    assert body["suggestion"]["send_identity_header"] is True  # a compose service name


async def test_srv15_a_server_json_becomes_a_draft(service_client):
    resp = await service_client.post(
        "/api/v1/upstreams:from-server-json",
        json={
            "document": {
                "name": "io.github.acme/weather",
                "remotes": [
                    {
                        "type": "streamable-http",
                        "url": "https://acme.example/mcp",
                        "headers": [{"name": "X-API-Key", "isRequired": True, "isSecret": True}],
                    }
                ],
            }
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["headers"][0]["name"] == "X-API-Key"


async def test_srv14_a_denied_forward_header_is_rejected_on_write(service_client):
    resp = await service_client.put(
        "/api/v1/upstreams/s",
        json={"name": "s", "url": "http://s/mcp", "forward_headers": {"cookie": "cookie"}},
    )
    assert resp.status_code == 422


async def test_fwd7_forwarding_authorization_is_reported(service_client):
    resp = await service_client.put(
        "/api/v1/upstreams/s",
        json={
            "name": "s",
            "url": "http://s/mcp",
            "forward_headers": {"authorization": "authorization"},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["forwards_caller_token"] is True
    assert body["connection_state"] == "unknown"


async def test_upo1_the_gateway_publishes_its_client_metadata_document(engine, redis):
    settings = hermetic_settings(public_url="https://gw.example")
    async with serving(engine, redis, settings=settings) as (http, _):
        resp = await http.get("/oauth/upstream/client.json")
    assert resp.status_code == 200
    document = resp.json()
    assert document["client_id"] == "https://gw.example/oauth/upstream/client.json"
    assert document["redirect_uris"] == ["https://gw.example/oauth/upstream/callback"]
    assert document["token_endpoint_auth_method"] == "none"
    assert document["application_type"] == "web"


async def test_fwd6_a_delegated_server_gets_an_introspectable_token_bound_to_it(engine, redis):
    await _seed_delegated(engine)
    key = await seed_api_key(engine, ENDPOINT_KEY, name="caller", kind=ApiKeyKind.ENDPOINT)
    await seed_api_key(engine, SERVICE_KEY)
    factory = RecordingFactory()
    async with serving(engine, redis, client_factory=factory) as (http, _):
        called = _result_of(await _call_forecast(http))
        assert called["result"]["content"][0]["text"] == "sunny in Bern", called
        bearer = factory.headers[-1]["Authorization"].removeprefix("Bearer ")
        assert bearer.startswith("bmcp_dt_") and bearer != ENDPOINT_KEY
        introspected = await http.post(
            "/oauth/introspect",
            data={"token": bearer},
            headers={"Authorization": f"Bearer {SERVICE_KEY}"},
        )
    body = introspected.json()
    assert body["active"] is True
    assert body["sub"] == f"api_key:{key.id}"
    assert body["aud"] == "http://weather:8000/mcp"
    assert body["token_use"] == "delegated"
    assert body["act"] == {"sub": "endpoint:main"}


async def test_srv12_a_refused_static_key_is_named_in_the_call_error(engine, redis):
    await _seed_delegated(engine, auth_mode=ServerAuthMode.STATIC_HEADERS)
    await seed_api_key(engine, ENDPOINT_KEY, name="caller", kind=ApiKeyKind.ENDPOINT)
    factory = RecordingFactory(refuse=ObservedResponse(status=401))
    async with serving(engine, redis, client_factory=factory) as (http, _):
        body = _result_of(await _call_forecast(http))
    assert "refused the gateway's credential" in body["error"]["message"]
    assert len(factory.headers) == 1  # no OAuth refresh-and-retry for a static credential


async def test_upo10_insufficient_scope_asks_the_caller_to_reconnect(engine, redis):
    await _seed_delegated(engine, auth_mode=ServerAuthMode.UPSTREAM_OAUTH)
    await seed_api_key(engine, ENDPOINT_KEY, name="caller", kind=ApiKeyKind.ENDPOINT)
    async with session_factory(engine)() as db:
        server = (await db.execute(select(McpServerRow))).scalars().one()
    cipher = token_cipher(EnvSettings(_env_file=None, token_encryption_keys=[KEY]))
    units = SqlAlchemyUnitOfWorkFactory(session_factory(engine), redis)
    storage = UpstreamTokenService(units, cipher, ValkeyRefreshLock(redis), StubProvider())
    await storage.save(server.id, None, UpstreamTokens(access_token="at", expires_in=3600))
    async with session_factory(engine)() as db:
        db.add(UpstreamOAuthClientRow(server_id=server.id, client_id="c", metadata_={}))
        await db.commit()

    refuse = ObservedResponse(
        status=403,
        challenge=UpstreamChallenge.parse('Bearer error="insufficient_scope", scope="admin"'),
    )
    factory = RecordingFactory(refuse=refuse)
    async with serving(
        engine,
        redis,
        settings=hermetic_settings(token_encryption_keys=[KEY]),
        client_factory=factory,
        upstream_oidc_provider=StubProvider(),
    ) as (http, _):
        body = _result_of(await _call_forecast(http))
    message = body["error"]["message"]
    assert "additional permission (admin)" in message
    assert "/oauth/upstream/weather/connect" in message
    assert len(factory.headers) == 1  # not retried: a new token would lack the scope too
    async with session_factory(engine)() as db:
        client = (await db.execute(select(UpstreamOAuthClientRow))).scalars().one()
    assert client.metadata_["step_up_scopes"] == ["admin"]


class StubProvider:
    async def discover(self, server_url):
        raise NeedsConnect("upstream", "no_oauth_metadata")

    async def register(self, meta, **kw):
        raise NeedsConnect("upstream", "no_client_config")

    def authorize_url(self, meta, **kw):
        return ""

    async def exchange(self, meta, **kw):
        return UpstreamTokens(access_token="at")

    async def refresh(self, meta, **kw):
        return UpstreamTokens(access_token="at")

    async def client_credentials(self, meta, **kw):
        return UpstreamTokens(access_token="at")
