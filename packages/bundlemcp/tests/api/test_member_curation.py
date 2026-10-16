"""Members' prompts and resources: discovered for curation, curated per bundle (UPS-24, BND-37,
BND-8, BND-7)."""

import asyncio

import pytest
from fastmcp import Client, FastMCP
from structlog.testing import capture_logs

from tests.conftest import SERVICE_KEY, seed_api_key, serving


def _member(prompts: list[str], resources: list[str]) -> FastMCP:
    server = FastMCP("weather")
    for name in prompts:
        server.prompt(name=name, description=f"The {name} prompt")(_prompt(name))
    for uri in resources:
        server.resource(uri, description=f"About {uri}")(_content(uri))
    return server


def _prompt(name: str):
    def prompt(city: str = "Bern") -> str:
        return f"{name} for {city}"

    return prompt


def _content(uri: str):
    def resource() -> str:
        return f"content of {uri}"

    return resource


async def _discovered(http, name: str) -> None:
    """Wait for the background discovery a create schedules, instead of racing it."""
    for _ in range(100):
        if (await http.get(f"/api/v1/upstreams/{name}")).json()["connection_state"] == "ready":
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"{name} was never discovered")


class Upstreams:
    """The in-process members, and which of them were contacted."""

    def __init__(self, **members: FastMCP) -> None:
        self.members = members
        self.contacted: list[str] = []

    def __call__(self, server, extra_headers, *, observer=None, **handlers):
        self.contacted.append(server.name)
        return Client(self.members[server.name])


@pytest.fixture
async def gateway(engine, redis):
    await seed_api_key(engine, SERVICE_KEY)
    upstreams = Upstreams(weather=_member(["daily", "weekly"], ["file:///a.txt", "file:///b.txt"]))
    async with serving(engine, redis, bearer=SERVICE_KEY, client_factory=upstreams) as (http, app):
        for bundle in ("b1", "b2"):
            await http.put(f"/api/v1/bundles/{bundle}", json={"name": bundle})
        await http.put("/api/v1/upstreams/weather", json={"name": "weather", "url": "http://w/mcp"})
        await _discovered(http, "weather")
        for bundle in ("b1", "b2"):
            await http.put(f"/api/v1/bundles/{bundle}/upstreams/weather", json={"enabled": True})
            endpoint = {"name": bundle, "bundle_name": bundle, "auth_modes": ["api_key"]}
            await http.put(f"/api/v1/endpoints/{bundle}", json=endpoint)
        yield http, upstreams


async def _rpc(http, endpoint: str, method: str, params: dict | None = None) -> dict:
    init = await http.post(
        f"/{endpoint}/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25", "capabilities": {}},
        },
    )
    session = init.headers["mcp-session-id"]
    resp = await http.post(
        f"/{endpoint}/mcp",
        headers={"Mcp-Session-Id": session},
        json={"jsonrpc": "2.0", "id": 2, "method": method, "params": params or {}},
    )
    return resp.json()


async def _entry(http, bundle: str, kind: str, key: str) -> dict:
    listed = (await http.get(f"/api/v1/bundles/{bundle}/member-{kind}s")).json()
    return next(entry for entry in listed if entry["key"] == key)


async def _curate(http, bundle: str, kind: str, key: str, **body) -> dict:
    entry = await _entry(http, bundle, kind, key)
    resp = await http.put(f"/api/v1/bundles/{bundle}/member-{kind}s/{entry['entry_id']}", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_ups24_prompts_and_resources_are_cached_at_discovery(gateway):
    """UPS-24: names, URIs, titles and descriptions are cached; no messages or content."""
    http, _ = gateway
    prompts = (await http.get("/api/v1/bundles/b1/member-prompts")).json()
    assert [(p["key"], p["presented_name"]) for p in prompts] == [
        ("daily", "weather__daily"),
        ("weekly", "weather__weekly"),
    ]
    assert prompts[0]["description"] == "The daily prompt" and prompts[0]["enabled"] is True
    resources = (await http.get("/api/v1/bundles/b1/member-resources")).json()
    assert [r["key"] for r in resources] == ["file:///a.txt", "file:///b.txt"]
    assert "content of" not in str(resources)


async def test_ups24_capability_not_advertised_not_asked(engine, redis):
    """UPS-24: an upstream advertising no prompts receives no prompts/list."""
    await seed_api_key(engine, SERVICE_KEY)
    tools_only = FastMCP("calc")

    @tools_only.tool
    def add(a: int, b: int) -> int:
        return a + b

    asked: list[str] = []

    class Recording(Client):
        @property
        def server_capabilities(self):
            # FastMCP advertises prompts even with none; this upstream does not
            advertised = super().server_capabilities
            return advertised.model_copy(update={"prompts": None, "resources": None})

        async def list_prompts(self, *args, **kwargs):  # pragma: no cover - must not run
            asked.append("prompts/list")
            return await super().list_prompts(*args, **kwargs)

    def factory(server, extra_headers, *, observer=None, **handlers):
        return Recording(tools_only)

    async with serving(engine, redis, bearer=SERVICE_KEY, client_factory=factory) as (http, _):
        await http.put("/api/v1/upstreams/calc", json={"name": "calc", "url": "http://c/mcp"})
        await _discovered(http, "calc")
    assert asked == []


async def test_ups24_failed_listing_keeps_cache(gateway):
    """UPS-24: a discovery whose prompt listing fails leaves the cached prompts as they were."""
    http, _ = gateway
    original = Client.list_prompts

    async def failing(self, *args, **kwargs):
        raise RuntimeError("listing failed")

    Client.list_prompts = failing  # type: ignore[method-assign]
    try:
        await http.post("/api/v1/upstreams/weather:refresh-tools")
    finally:
        Client.list_prompts = original  # type: ignore[method-assign]
    prompts = (await http.get("/api/v1/bundles/b1/member-prompts")).json()
    assert [p["key"] for p in prompts] == ["daily", "weekly"]
    assert not any(p["stale"] for p in prompts)


async def test_ups24_long_listing_truncated_and_logged(engine, redis, monkeypatch):
    """UPS-24: only the bound is cached, and a warning names the server."""
    from bundlemcp.infrastructure.fastmcp import upstream_probe

    monkeypatch.setattr(upstream_probe, "MEMBER_LISTING_LIMIT", 2)
    await seed_api_key(engine, SERVICE_KEY)
    many = Upstreams(weather=_member([], [f"file:///{n}.txt" for n in range(5)]))
    async with serving(engine, redis, bearer=SERVICE_KEY, client_factory=many) as (http, _):
        await http.put("/api/v1/bundles/b1", json={"name": "b1"})
        with capture_logs() as logs:
            await http.put(
                "/api/v1/upstreams/weather", json={"name": "weather", "url": "http://w/mcp"}
            )
            await _discovered(http, "weather")
        await http.put("/api/v1/bundles/b1/upstreams/weather", json={"enabled": True})
        resources = (await http.get("/api/v1/bundles/b1/member-resources")).json()
    assert len(resources) == 2
    truncated = [entry for entry in logs if entry["event"] == "discovery.listing_truncated"]
    assert truncated and truncated[0]["server"] == "weather"


async def test_bnd37_disabled_member_prompt_hidden_and_refused(gateway):
    """BND-37: a disabled prompt is not listed, and getting it never contacts the member."""
    http, upstreams = gateway
    await _curate(http, "b1", "prompt", "daily", enabled=False)
    listed = (await _rpc(http, "b1", "prompts/list"))["result"]["prompts"]
    assert [p["name"] for p in listed] == ["weather__weekly"]
    upstreams.contacted.clear()
    got = await _rpc(http, "b1", "prompts/get", {"name": "weather__daily"})
    assert got["error"]["code"] == -32602
    assert upstreams.contacted == []


async def test_bnd37_disabled_member_resource_hidden_and_refused(gateway):
    """BND-37: a disabled resource is not listed, and reading it never contacts the member."""
    http, upstreams = gateway
    await _curate(http, "b1", "resource", "file:///a.txt", enabled=False)
    listed = (await _rpc(http, "b1", "resources/list"))["result"]["resources"]
    assert [r["uri"] for r in listed] == ["file:///b.txt"]
    upstreams.contacted.clear()
    read = await _rpc(http, "b1", "resources/read", {"uri": "file:///a.txt"})
    assert "error" in read
    assert upstreams.contacted == []


async def test_bnd37_title_override_presented(gateway):
    """BND-37: an override title is presented; the name and arguments stay the member's."""
    http, _ = gateway
    await _curate(http, "b1", "prompt", "daily", override_title="Morning forecast")
    listed = (await _rpc(http, "b1", "prompts/list"))["result"]["prompts"]
    daily = next(p for p in listed if p["name"] == "weather__daily")
    assert daily["title"] == "Morning forecast"
    assert [a["name"] for a in daily["arguments"]] == ["city"]


async def test_bnd37_curation_is_per_bundle(gateway):
    """BND-37: disabling in b1 leaves the prompt listed in b2."""
    http, _ = gateway
    await _curate(http, "b1", "prompt", "daily", enabled=False)
    listed = (await _rpc(http, "b2", "prompts/list"))["result"]["prompts"]
    assert "weather__daily" in [p["name"] for p in listed]


async def test_bnd37_curation_over_management_api(gateway):
    """BND-37: the next listing reports the curation, for prompts and resources alike."""
    http, _ = gateway
    await _curate(http, "b1", "prompt", "weekly", enabled=False)
    await _curate(http, "b1", "resource", "file:///b.txt", override_description="Notes")
    assert (await _entry(http, "b1", "prompt", "weekly"))["enabled"] is False
    assert (await _entry(http, "b1", "resource", "file:///b.txt"))["override_description"] == (
        "Notes"
    )
    resp = await http.put(
        "/api/v1/bundles/b1/member-prompts/00000000-0000-0000-0000-000000000000",
        json={"enabled": False},
    )
    assert resp.status_code == 404


async def test_bnd8_served_lists_stay_live(gateway):
    """BND-8: a prompt the member no longer lists is not served, whatever the cache holds."""
    http, upstreams = gateway
    upstreams.members["weather"] = _member(["weekly"], [])
    listed = (await _rpc(http, "b1", "prompts/list"))["result"]["prompts"]
    assert [p["name"] for p in listed] == ["weather__weekly"]
    cached = (await http.get("/api/v1/bundles/b1/member-prompts")).json()
    assert {p["key"] for p in cached} == {"daily", "weekly"}


async def test_bnd7_member_prompt_curation_notifies(gateway, redis):
    """BND-7: curating a member prompt announces the bundle's prompt list as changed."""
    http, _ = gateway
    pubsub = redis.pubsub()
    await pubsub.subscribe("bmcp:invalidate")
    await pubsub.get_message(timeout=1)
    await _curate(http, "b1", "prompt", "daily", enabled=False)
    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)
    await pubsub.aclose()
    assert message is not None
    assert '"entity_type":"bundle_prompt"' in message["data"] and '"key":"b1"' in message["data"]
