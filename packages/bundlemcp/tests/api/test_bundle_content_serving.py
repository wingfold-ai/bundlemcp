"""Bundle-owned prompts and resources (spec 17) served over MCP, beside member passthrough.

The member upstream is in-process FastMCP behind a recording client factory, so
each test can assert that a bundle-owned request contacted no upstream at all.
"""

from contextlib import asynccontextmanager
from typing import Any

import pytest
from bundlemcp.domain.access.api_key_kind import ApiKeyKind
from bundlemcp.domain.shared.secrets import display_prefix, hash_token
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.api_key_row import ApiKeyRow
from bundlemcp.infrastructure.postgres.rows.bundle_prompt_row import BundlePromptRow
from bundlemcp.infrastructure.postgres.rows.bundle_resource_row import BundleResourceRow
from bundlemcp.infrastructure.postgres.rows.bundle_row import BundleRow
from bundlemcp.infrastructure.postgres.rows.bundle_server_row import BundleServerRow
from bundlemcp.infrastructure.postgres.rows.endpoint_row import EndpointRow
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from fastmcp import Client, FastMCP
from mcp.types import CLIENT_CAPABILITIES_META_KEY, PROTOCOL_VERSION_META_KEY
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import ENDPOINT_KEY, serving

member = FastMCP("python")


@member.prompt
def greet(name: str) -> str:
    """A member prompt."""
    return f"Hello {name}"


@member.resource("res://member")
def member_resource() -> str:
    return "member content"


@member.resource("bundle://resources/style")
def impostor() -> str:
    """A member resource in the bundle's own scheme: shadowed, never served (BPR-7)."""
    return "member pretending to be the bundle"


STYLE = "# House style\n\nUse blue."


async def _seed(engine: AsyncEngine) -> None:
    async with session_factory(engine)() as db:
        db.add(
            ApiKeyRow(
                name="k",
                key_hash=hash_token(ENDPOINT_KEY),
                key_prefix=display_prefix(ENDPOINT_KEY),
                kind=ApiKeyKind.ENDPOINT,
            )
        )
        python = McpServerRow(
            name="python",
            url="http://python/mcp",
            capabilities={"prompts": {}, "resources": {}, "completions": {}},
        )
        main = BundleRow(name="main")
        solo = BundleRow(name="solo")  # a bundle with no member at all
        db.add_all([python, main, solo])
        await db.commit()
        for row in (python, main, solo):
            await db.refresh(row)
        db.add_all(
            [
                BundleServerRow(bundle_id=main.id, server_id=python.id),
                EndpointRow(name="main", bundle_id=main.id, auth_modes=["api_key"]),
                EndpointRow(name="solo", bundle_id=solo.id, auth_modes=["api_key"]),
            ]
        )
        for bundle in (main, solo):
            db.add_all(
                [
                    BundleResourceRow(
                        bundle_id=bundle.id,
                        name="style",
                        title="House style",
                        content=STYLE,
                        size_bytes=len(STYLE.encode()),
                    ),
                    BundlePromptRow(
                        bundle_id=bundle.id,
                        name="plot",
                        description="Plot a series",
                        arguments=[
                            {"name": "series", "required": True},
                            {"name": "kind", "values": ["bar", "Bubble", "line"]},
                        ],
                        messages=[
                            {"role": "user", "text": "Plot {{series}} as {{kind}}."},
                            {"role": "user", "resource": "style"},
                        ],
                    ),
                    BundlePromptRow(
                        bundle_id=bundle.id,
                        name="about",
                        messages=[{"role": "assistant", "text": "I draw charts."}],
                    ),
                ]
            )
        await db.commit()


@asynccontextmanager
async def _running(engine, redis):
    contacted: list[str] = []

    def factory(server, extra_headers, *, observer=None, **handlers):
        contacted.append(server.name)
        return Client(member)

    await _seed(engine)
    async with serving(engine, redis, bearer=ENDPOINT_KEY, client_factory=factory) as (http, _):
        yield http, contacted


@pytest.fixture
async def gateway(engine, redis):
    async with _running(engine, redis) as running:
        yield running


async def _initialize(http, endpoint: str) -> tuple[str, dict[str, Any]]:
    resp = await http.post(
        f"/{endpoint}/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25", "capabilities": {}},
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.headers["mcp-session-id"], resp.json()["result"]


async def _rpc(http, method: str, params: dict | None = None, endpoint: str = "main"):
    session, _ = await _initialize(http, endpoint)
    resp = await http.post(
        f"/{endpoint}/mcp",
        headers={"Mcp-Session-Id": session},
        json={"jsonrpc": "2.0", "id": 2, "method": method, "params": params or {}},
    )
    return resp.json()


async def test_prompts_list_puts_the_bundles_own_first(gateway):
    """BPR-9: bundle prompts in name order, unprefixed, then the members' prefixed ones."""
    http, _ = gateway
    prompts = (await _rpc(http, "prompts/list"))["result"]["prompts"]
    assert [p["name"] for p in prompts] == ["about", "plot", "python__greet"]
    plot = prompts[1]
    assert plot["description"] == "Plot a series"
    assert plot["arguments"] == [
        {"name": "series", "required": True},
        {"name": "kind", "required": False},
    ]


async def test_prompts_get_renders_without_contacting_a_member(gateway):
    """BPR-3, BPR-8: substitution, an embedded resource, and no upstream contact."""
    http, contacted = gateway
    result = (
        await _rpc(http, "prompts/get", {"name": "plot", "arguments": {"series": "revenue"}})
    )["result"]
    assert result["description"] == "Plot a series"
    text, embed = result["messages"]
    assert text == {"role": "user", "content": {"type": "text", "text": "Plot revenue as ."}}
    assert embed["content"] == {
        "type": "resource",
        "resource": {
            "uri": "bundle://resources/style",
            "mimeType": "text/markdown",
            "text": STYLE,
        },
    }
    assert contacted == []


async def test_prompts_get_names_the_missing_required_argument(gateway):
    """BPR-4"""
    http, _ = gateway
    error = (await _rpc(http, "prompts/get", {"name": "plot"}))["error"]
    assert error["code"] == -32602 and "series" in error["message"]


async def test_unknown_unprefixed_prompt_never_falls_through(gateway):
    """BPR-9: a name without `__` is the bundle's alone; an unknown one asks no member."""
    http, contacted = gateway
    error = (await _rpc(http, "prompts/get", {"name": "greet"}))["error"]
    assert error["code"] == -32602
    assert contacted == []


async def test_member_prompt_still_passes_through(gateway):
    """BND-8 is unchanged for prefixed names."""
    http, contacted = gateway
    result = (
        await _rpc(http, "prompts/get", {"name": "python__greet", "arguments": {"name": "Ada"}})
    )["result"]
    assert "Ada" in str(result["messages"])
    assert contacted == ["python"]


async def test_resources_list_puts_the_bundles_own_first_and_shadows_its_scheme(gateway):
    """BPR-9, BPR-7: a member URI in the bundle: scheme is dropped from the list."""
    http, _ = gateway
    resources = (await _rpc(http, "resources/list"))["result"]["resources"]
    assert [r["uri"] for r in resources] == ["bundle://resources/style", "res://member"]
    assert resources[0]["name"] == "style"
    assert resources[0]["title"] == "House style"
    assert resources[0]["size"] == len(STYLE.encode())


async def test_resources_read_serves_the_bundles_own(gateway):
    """BPR-8, BPR-9: the bundle answers its own scheme; the member impostor is unreachable."""
    http, contacted = gateway
    contents = (await _rpc(http, "resources/read", {"uri": "bundle://resources/style"}))["result"][
        "contents"
    ]
    assert contents == [
        {"uri": "bundle://resources/style", "mimeType": "text/markdown", "text": STYLE}
    ]
    assert contacted == []


async def test_unknown_bundle_uri_is_not_found_without_asking_members(gateway):
    """BPR-9"""
    http, contacted = gateway
    error = (await _rpc(http, "resources/read", {"uri": "bundle://resources/nope"}))["error"]
    assert error["code"] == -32002
    assert contacted == []


async def test_completion_answers_from_suggested_values(gateway):
    """BPR-5: case-insensitive prefix match, answered by the gateway alone."""
    http, contacted = gateway
    completion = (
        await _rpc(
            http,
            "completion/complete",
            {
                "ref": {"type": "ref/prompt", "name": "plot"},
                "argument": {"name": "kind", "value": "b"},
            },
        )
    )["result"]["completion"]
    assert completion == {"values": ["bar", "Bubble"], "total": 2, "hasMore": False}
    free = (
        await _rpc(
            http,
            "completion/complete",
            {
                "ref": {"type": "ref/prompt", "name": "plot"},
                "argument": {"name": "series", "value": "r"},
            },
        )
    )["result"]["completion"]
    assert free["values"] == []
    assert contacted == []


async def test_bundle_without_members_serves_prompts_and_resources(gateway):
    """BPR-10: an endpoint over a member-less bundle advertises and serves its own content."""
    http, contacted = gateway
    _, result = await _initialize(http, "solo")
    caps = result["capabilities"]
    assert caps["prompts"] == {"listChanged": True}
    assert caps["resources"] == {"listChanged": True}
    assert caps["completions"] == {}
    prompts = (await _rpc(http, "prompts/list", endpoint="solo"))["result"]["prompts"]
    assert [p["name"] for p in prompts] == ["about", "plot"]
    assert contacted == []


async def test_bundle_resource_read_is_publicly_cacheable(gateway):
    """BPR-12: the same content for every caller, so it carries the list TTL, public."""
    http, _ = gateway
    params = {
        "uri": "bundle://resources/style",
        "_meta": {PROTOCOL_VERSION_META_KEY: "2026-07-28", CLIENT_CAPABILITIES_META_KEY: {}},
    }
    resp = await http.post(
        "/solo/mcp",
        headers={
            "MCP-Protocol-Version": "2026-07-28",
            "Mcp-Method": "resources/read",
            "Mcp-Name": "bundle://resources/style",
        },
        json={"jsonrpc": "2.0", "id": 1, "method": "resources/read", "params": params},
    )
    result = resp.json()["result"]
    assert result["cacheScope"] == "public" and result["ttlMs"] == 300000
