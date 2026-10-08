"""The identity provider's subject reaches the metering hook, introspection and X-MCP-User.

Spec 31 (MID-1), spec 20 (OAS-5), spec 24 (FWD-3, FWD-6), through the ASGI app with an
OAuth user and an API key calling the same endpoint.
"""

import json
from datetime import timedelta

import pytest
from bundlemcp.application.metering.meter_context import MeterContext
from bundlemcp.application.metering.meter_decision import MeterDecision
from bundlemcp.domain.access.api_key import ApiKey
from bundlemcp.domain.access.api_key_kind import ApiKeyKind
from bundlemcp.domain.access.identity_subject import IdentitySubject
from bundlemcp.domain.servers.server_auth_mode import ServerAuthMode
from bundlemcp.domain.shared.clock import utcnow
from bundlemcp.domain.shared.secrets import hash_token
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.bundle_row import BundleRow
from bundlemcp.infrastructure.postgres.rows.bundle_server_row import BundleServerRow
from bundlemcp.infrastructure.postgres.rows.endpoint_row import EndpointRow
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.postgres.rows.oauth_access_token_row import OAuthAccessTokenRow
from bundlemcp.infrastructure.postgres.rows.oauth_client_row import OAuthClientRow
from bundlemcp.infrastructure.postgres.rows.tool_row import ToolRow
from bundlemcp.infrastructure.postgres.rows.user_row import UserRow
from fastmcp import Client, FastMCP
from pydantic import BaseModel, Field, ValidationError

from tests.conftest import ENDPOINT_KEY, SERVICE_KEY, hermetic_settings, seed_api_key, serving

ISSUER = "http://idp/realms/main"
IDP_SUB = "3f1c9a2e-keycloak-subject"
USER_TOKEN = "bmcp_at_idp-subject-user-token"

weather = FastMCP("weather")


@weather.tool
def forecast(city: str) -> str:
    """Tomorrow's forecast."""
    return f"sunny in {city}"


class RecordingFactory:
    """In-process upstream that remembers the headers of every request."""

    def __init__(self) -> None:
        self.headers: list[dict[str, str]] = []

    def __call__(self, server, extra_headers, *, observer=None, **handlers):
        self.headers.append(dict(extra_headers))
        return Client(weather, **handlers)


class RecordingHook:
    """Metering hook double that allows every call and keeps its context."""

    def __init__(self) -> None:
        self.contexts: list[MeterContext] = []

    async def pre_call(self, ctx: MeterContext) -> MeterDecision:
        self.contexts.append(ctx)
        return MeterDecision(allowed=True)

    async def post_call(self, ctx: MeterContext, status: str, duration_ms: int) -> None:
        pass


class Seeded(BaseModel):
    """What a test needs to recognise its two callers."""

    user_id: str = Field(description="The gateway's own id of the seeded OAuth user")
    key: ApiKey = Field(description="The endpoint API key the second caller presents")


async def _seed(engine, auth_mode: ServerAuthMode) -> Seeded:
    async with session_factory(engine)() as db:
        user = UserRow(oidc_issuer=ISSUER, oidc_sub=IDP_SUB, email="alice@example.com")
        server = McpServerRow(name="weather", url="http://weather:8000/mcp", auth_mode=auth_mode)
        bundle = BundleRow(name="main")
        db.add_all([user, server, bundle])
        await db.commit()
        for row in (user, server, bundle):
            await db.refresh(row)
        endpoint = EndpointRow(name="main", bundle_id=bundle.id, auth_modes=["oauth", "api_key"])
        db.add_all(
            [
                endpoint,
                BundleServerRow(bundle_id=bundle.id, server_id=server.id),
                ToolRow(server_id=server.id, name="forecast", schema_hash="h", input_schema={}),
                OAuthClientRow(client_id="claude", redirect_uris=["https://c/cb"]),
            ]
        )
        await db.commit()
        await db.refresh(endpoint)
        db.add(
            OAuthAccessTokenRow(
                access_token_hash=hash_token(USER_TOKEN),
                client_id="claude",
                user_id=user.id,
                endpoint_id=endpoint.id,
                expires_at=utcnow() + timedelta(hours=1),
            )
        )
        await db.commit()
        user_id = str(user.id)
    key = await seed_api_key(engine, ENDPOINT_KEY, name="caller", kind=ApiKeyKind.ENDPOINT)
    await seed_api_key(engine, SERVICE_KEY)
    return Seeded(user_id=user_id, key=key)


async def _call_forecast(http, bearer: str) -> dict:
    response = await http.post(
        "/main/mcp",
        headers={
            "Authorization": f"Bearer {bearer}",
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
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        data = [
            line.removeprefix("data:").strip()
            for line in response.text.splitlines()
            if line.startswith("data:")
        ]
        body = json.loads(data[-1])
    else:
        body = response.json()
    assert body["result"]["content"][0]["text"] == "sunny in Bern", body
    return body


async def _introspect(http, token: str) -> dict:
    response = await http.post(
        "/oauth/introspect",
        data={"token": token},
        headers={"Authorization": f"Bearer {SERVICE_KEY}"},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_mid1_meter_context_carries_the_idp_subject_of_a_user_and_none_for_a_key(
    engine, redis
):
    seeded = await _seed(engine, ServerAuthMode.STATIC_HEADERS)
    hook = RecordingHook()
    async with serving(engine, redis, client_factory=RecordingFactory(), metering_hook=hook) as (
        http,
        _,
    ):
        await _call_forecast(http, USER_TOKEN)
        await _call_forecast(http, ENDPOINT_KEY)
    user_ctx, key_ctx = hook.contexts
    assert (user_ctx.sub, user_ctx.oidc_issuer, user_ctx.oidc_sub) == (
        seeded.user_id,
        ISSUER,
        IDP_SUB,
    )
    assert (key_ctx.sub, key_ctx.oidc_issuer, key_ctx.oidc_sub) == (
        f"api_key:{seeded.key.id}",
        None,
        None,
    )


async def test_oas5_a_user_token_introspects_with_the_idp_subject(engine, redis):
    seeded = await _seed(engine, ServerAuthMode.STATIC_HEADERS)
    async with serving(engine, redis, client_factory=RecordingFactory()) as (http, _):
        body = await _introspect(http, USER_TOKEN)
    assert body["active"] is True
    assert body["sub"] == seeded.user_id  # unchanged: the gateway's own user id
    assert (body["oidc_iss"], body["oidc_sub"]) == (ISSUER, IDP_SUB)


async def test_oas5_an_api_key_introspects_without_an_idp_subject(engine, redis):
    seeded = await _seed(engine, ServerAuthMode.STATIC_HEADERS)
    async with serving(engine, redis, client_factory=RecordingFactory()) as (http, _):
        body = await _introspect(http, ENDPOINT_KEY)
    assert body["sub"] == f"api_key:{seeded.key.id}"
    assert "oidc_iss" not in body and "oidc_sub" not in body


async def test_oas5_fwd6_a_token_delegated_for_a_user_introspects_with_the_idp_subject(
    engine, redis
):
    seeded = await _seed(engine, ServerAuthMode.DELEGATED_TOKEN)
    factory = RecordingFactory()
    async with serving(engine, redis, client_factory=factory) as (http, _):
        await _call_forecast(http, USER_TOKEN)
        user_body = await _introspect(
            http, factory.headers[-1]["Authorization"].removeprefix("Bearer ")
        )
        await _call_forecast(http, ENDPOINT_KEY)
        key_body = await _introspect(
            http, factory.headers[-1]["Authorization"].removeprefix("Bearer ")
        )
    assert user_body["token_use"] == "delegated"
    assert user_body["sub"] == seeded.user_id
    assert (user_body["oidc_iss"], user_body["oidc_sub"]) == (ISSUER, IDP_SUB)
    assert key_body["token_use"] == "delegated"
    assert "oidc_iss" not in key_body and "oidc_sub" not in key_body


@pytest.mark.parametrize(
    ("identity_subject", "user_header"),
    [(IdentitySubject.INTERNAL, None), (IdentitySubject.OIDC, IDP_SUB)],
)
async def test_fwd3_x_mcp_user_follows_the_identity_subject_setting(
    engine, redis, identity_subject, user_header
):
    seeded = await _seed(engine, ServerAuthMode.STATIC_HEADERS)
    factory = RecordingFactory()
    settings = hermetic_settings(identity_subject=identity_subject)
    async with serving(engine, redis, settings=settings, client_factory=factory) as (http, _):
        await _call_forecast(http, USER_TOKEN)
        await _call_forecast(http, ENDPOINT_KEY)
    user_headers, key_headers = factory.headers
    assert user_headers["X-MCP-User"] == (user_header or seeded.user_id)
    assert key_headers["X-MCP-User"] == f"api_key:{seeded.key.id}"  # a key is a key either way


def test_fwd3_identity_subject_defaults_to_the_internal_user_id(monkeypatch):
    assert hermetic_settings().identity_subject is IdentitySubject.INTERNAL
    monkeypatch.setenv("BUNDLEMCP_IDENTITY_SUBJECT", "oidc")
    assert hermetic_settings().identity_subject is IdentitySubject.OIDC
    monkeypatch.setenv("BUNDLEMCP_IDENTITY_SUBJECT", "email")
    with pytest.raises(ValidationError):
        hermetic_settings()
