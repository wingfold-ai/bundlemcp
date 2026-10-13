"""Endpoint profiles taken from the registered catalogue, end to end (EP-13, EP-14, BND-13).

The app is built with a catalogue whose ``default`` profile is a test preset: it
requires an API key and hides any tool named ``secret``. Every place a profile
matters — the profile listing, endpoint writes, ``tools/list`` and ``tools/call``
— must follow it, which shows that nothing branches on a profile's name.
"""

import json
from contextlib import asynccontextmanager

from bundlemcp.domain.access.api_key_kind import ApiKeyKind
from bundlemcp.domain.bundles.presented_tool import PresentedTool
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.domain.endpoints.endpoint_profile import EndpointProfile
from bundlemcp.domain.endpoints.profiles import (
    ChatgptProfile,
    ClaudeProfile,
    ProfileCatalog,
    ProfileRuleViolation,
)
from bundlemcp.domain.shared.secrets import display_prefix, hash_token
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.api_key_row import ApiKeyRow
from bundlemcp.infrastructure.postgres.rows.bundle_row import BundleRow
from bundlemcp.infrastructure.postgres.rows.bundle_server_row import BundleServerRow
from bundlemcp.infrastructure.postgres.rows.bundle_tool_row import BundleToolRow
from bundlemcp.infrastructure.postgres.rows.endpoint_row import EndpointRow
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.postgres.rows.tool_row import ToolRow
from fastmcp import Client, FastMCP
from sqlmodel import select

from tests.conftest import ENDPOINT_KEY, SERVICE_KEY, serving

upstream = FastMCP("vault")
contacted: list[str] = []


@upstream.tool
def secret() -> str:
    """Never served by the test profile."""
    return "leaked"


@upstream.tool
def public(text: str) -> str:
    return f"public:{text}"


def upstream_factory(server, extra_headers, *, observer=None, **handlers):
    contacted.append(server.name)
    return Client(upstream)


class HidingProfile:
    """A test preset registered as ``default``: API keys only, and ``secret`` is hidden."""

    name = EndpointProfile.DEFAULT
    description = "Test preset: hides the secret tool"
    warning = "registered by the test"

    def check_auth_modes(self, modes: frozenset[EndpointAuthMode]) -> None:
        if EndpointAuthMode.API_KEY not in modes:
            raise ProfileRuleViolation("hiding profile requires api_key")

    def transform(self, tool: PresentedTool) -> PresentedTool | None:
        return None if tool.tool.name == "secret" else tool


class RecordingProfile(HidingProfile):
    """Hides nothing, and records every tool it is asked to transform."""

    seen: list[str] = []

    def transform(self, tool: PresentedTool) -> PresentedTool | None:
        self.seen.append(tool.tool.name)
        return tool


def catalog(default) -> ProfileCatalog:
    return ProfileCatalog(
        presets={
            EndpointProfile.DEFAULT: default,
            EndpointProfile.CLAUDE: ClaudeProfile(),
            EndpointProfile.CHATGPT: ChatgptProfile(),
        }
    )


async def _seed(engine) -> None:
    async with session_factory(engine)() as db:
        for key, kind in ((ENDPOINT_KEY, ApiKeyKind.ENDPOINT), (SERVICE_KEY, ApiKeyKind.SERVICE)):
            db.add(
                ApiKeyRow(
                    name=kind.value,
                    key_hash=hash_token(key),
                    key_prefix=display_prefix(key),
                    kind=kind,
                )
            )
        vault = McpServerRow(name="vault", url="http://vault/mcp")
        bundle = BundleRow(name="main")
        db.add_all([vault, bundle])
        await db.commit()
        for row in (vault, bundle):
            await db.refresh(row)
        db.add_all(
            [
                BundleServerRow(bundle_id=bundle.id, server_id=vault.id),
                EndpointRow(name="main", bundle_id=bundle.id, auth_modes=["api_key"]),
                ToolRow(server_id=vault.id, name="secret", schema_hash="h", input_schema={}),
                ToolRow(server_id=vault.id, name="public", schema_hash="h", input_schema={}),
            ]
        )
        await db.commit()


@asynccontextmanager
async def _running(engine, redis, profile):
    contacted.clear()
    await _seed(engine)
    async with serving(
        engine,
        redis,
        bearer=SERVICE_KEY,
        client_factory=upstream_factory,
        profiles=catalog(profile),
    ) as running:
        yield running


async def _rpc(http, method: str, params: dict | None = None):
    resp = await http.post(
        "/main/mcp",
        headers={
            "Authorization": f"Bearer {ENDPOINT_KEY}",
            "MCP-Protocol-Version": "2026-07-28",
            "Mcp-Method": method,
            # a call mirrors the tool name in a header too
            **({"Mcp-Name": params["name"]} if params and "name" in params else {}),
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": {
                **(params or {}),
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                    "io.modelcontextprotocol/clientCapabilities": {},
                },
            },
        },
    )
    if resp.headers.get("content-type", "").startswith("text/event-stream"):
        # a served call streams; its result is the last event
        data = [line[5:].strip() for line in resp.text.splitlines() if line.startswith("data:")]
        return json.loads(data[-1])
    return resp.json()


async def test_ep14_registered_profile_used_everywhere(engine, redis):
    """The registered preset drives the listing, endpoint writes and the served tools."""
    async with _running(engine, redis, HidingProfile()) as (http, _app):
        listing = (await http.get("/api/v1/endpoints/profiles")).json()
        default = next(p for p in listing if p["name"] == "default")
        assert default["description"] == "Test preset: hides the secret tool"
        assert default["warning"] == "registered by the test"

        refused = await http.put(
            "/api/v1/endpoints/main",
            json={"name": "main", "bundle_name": "main", "auth_modes": ["oauth"]},
        )
        assert refused.status_code == 422
        assert "hiding profile" in refused.text
        accepted = await http.put(
            "/api/v1/endpoints/main",
            json={"name": "main", "bundle_name": "main", "auth_modes": ["api_key", "oauth"]},
        )
        assert accepted.status_code == 200

        tools = (await _rpc(http, "tools/list"))["result"]["tools"]
        assert [t["name"] for t in tools] == ["vault__public"]


async def test_ep13_profile_drop_rejected_on_call(engine, redis):
    """A tool the profile hides is rejected on call like a disabled one; no upstream is asked."""
    async with _running(engine, redis, HidingProfile()) as (http, _app):
        error = (await _rpc(http, "tools/call", {"name": "vault__secret", "arguments": {}}))[
            "error"
        ]
        assert error["code"] == -32602
        assert "Unknown tool" in error["message"]
        assert contacted == []

        served = await _rpc(
            http, "tools/call", {"name": "vault__public", "arguments": {"text": "x"}}
        )
        assert served["result"]["content"][0]["text"] == "public:x"


async def test_bnd13_disabled_tool_never_reaches_profile(engine, redis):
    """Curation filters a disabled tool before the profile transform ever sees it."""
    RecordingProfile.seen = []
    async with _running(engine, redis, RecordingProfile()) as (http, app):
        async with app.state.container.session_factory() as db:
            bundle = (await db.execute(select(BundleRow))).scalar_one()
            tool = (await db.execute(select(ToolRow).where(ToolRow.name == "public"))).scalar_one()
            db.add(BundleToolRow(bundle_id=bundle.id, tool_id=tool.id, enabled=False))
            await db.commit()

        tools = (await _rpc(http, "tools/list"))["result"]["tools"]
        assert [t["name"] for t in tools] == ["vault__secret"]
        assert "public" not in RecordingProfile.seen
        assert "secret" in RecordingProfile.seen
        error = (await _rpc(http, "tools/call", {"name": "vault__public", "arguments": {}}))[
            "error"
        ]
        assert error["code"] == -32602
        assert contacted == []
