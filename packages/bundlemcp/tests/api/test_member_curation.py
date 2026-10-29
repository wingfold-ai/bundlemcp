"""Members' prompts and resources: discovered, stored, served and curated per bundle (UPS-24,
UPS-38, BND-37, BND-8, BND-7, BND-38)."""

import asyncio

import pytest
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.bundle_row import BundleRow
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from fastmcp import Client, FastMCP
from structlog.testing import capture_logs

from tests.conftest import SERVICE_KEY, background_probes_done, seed_api_key, serving


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
    await background_probes_done()
    assert (await http.get(f"/api/v1/upstreams/{name}")).json()["connection_state"] == "ready"


class Upstreams:
    """The in-process members, and which of them were contacted with which headers."""

    def __init__(self, **members: FastMCP) -> None:
        self.members = members
        self.contacted: list[str] = []
        self.headers: list[dict[str, str]] = []

    def __call__(self, server, extra_headers, *, observer=None, **handlers):
        self.contacted.append(server.name)
        self.headers.append(dict(extra_headers))
        return Client(self.members[server.name])


@pytest.fixture
async def gateway(engine, redis):
    await seed_api_key(engine, SERVICE_KEY)
    upstreams = Upstreams(weather=_member(["daily", "weekly"], ["file:///a.txt", "file:///b.txt"]))
    async with serving(engine, redis, bearer=SERVICE_KEY, client_factory=upstreams) as (http, app):
        for bundle in ("b1", "b2"):
            await http.put(f"/api/v1/bundles/{bundle}", json={"name": bundle})
        # FastMCP marks its lists private by default; the operator says they are not
        weather = {"name": "weather", "url": "http://w/mcp", "listing_snapshot": "shared"}
        await http.put("/api/v1/upstreams/weather", json=weather)
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
    """UPS-24: an upstream advertising neither prompts nor resources is asked for no listing."""
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

        async def list_prompts_mcp(self, *args, **kwargs):  # pragma: no cover - must not run
            asked.append("prompts/list")
            return await super().list_prompts_mcp(*args, **kwargs)

        async def list_resources_mcp(self, *args, **kwargs):  # pragma: no cover - must not run
            asked.append("resources/list")
            return await super().list_resources_mcp(*args, **kwargs)

        async def list_resource_templates_mcp(
            self, *args, **kwargs
        ):  # pragma: no cover - must not run
            asked.append("resources/templates/list")
            return await super().list_resource_templates_mcp(*args, **kwargs)

    def factory(server, extra_headers, *, observer=None, **handlers):
        return Recording(tools_only)

    async with serving(engine, redis, bearer=SERVICE_KEY, client_factory=factory) as (http, _):
        await http.put("/api/v1/upstreams/calc", json={"name": "calc", "url": "http://c/mcp"})
        await _discovered(http, "calc")
    assert asked == []


async def test_ups24_failed_listing_keeps_cache(gateway):
    """UPS-24: a discovery whose prompt listing fails leaves the cached prompts and the stored
    prompt listing as they were."""
    http, upstreams = gateway
    upstreams.members["weather"] = _member(["weekly"], [])
    original = Client.list_prompts_mcp

    async def failing(self, *args, **kwargs):
        raise RuntimeError("listing failed")

    Client.list_prompts_mcp = failing  # type: ignore[method-assign]
    try:
        await http.post("/api/v1/upstreams/weather:refresh-tools")
    finally:
        Client.list_prompts_mcp = original  # type: ignore[method-assign]
    prompts = (await http.get("/api/v1/bundles/b1/member-prompts")).json()
    assert [p["key"] for p in prompts] == ["daily", "weekly"]
    assert not any(p["stale"] for p in prompts)
    listed = (await _rpc(http, "b1", "prompts/list"))["result"]["prompts"]
    assert [p["name"] for p in listed] == ["weather__daily", "weather__weekly"]


async def test_ups24_long_listing_truncated_and_logged(engine, redis, monkeypatch):
    """UPS-24: only the bound is cached, the stored listing is marked incomplete and not served,
    and a warning names the server."""
    from bundlemcp.infrastructure.fastmcp import upstream_probe

    monkeypatch.setattr(upstream_probe, "MEMBER_LISTING_LIMIT", 2)
    await seed_api_key(engine, SERVICE_KEY)
    many = Upstreams(weather=_member([], [f"file:///{n}.txt" for n in range(5)]))
    weather = {"name": "weather", "url": "http://w/mcp", "listing_snapshot": "shared"}
    async with serving(engine, redis, bearer=SERVICE_KEY, client_factory=many) as (http, _):
        await http.put("/api/v1/bundles/b1", json={"name": "b1"})
        with capture_logs() as logs:
            await http.put("/api/v1/upstreams/weather", json=weather)
            await _discovered(http, "weather")
        await http.put("/api/v1/bundles/b1/upstreams/weather", json={"enabled": True})
        resources = (await http.get("/api/v1/bundles/b1/member-resources")).json()
        endpoint = {"name": "b1", "bundle_name": "b1", "auth_modes": ["api_key"]}
        await http.put("/api/v1/endpoints/b1", json=endpoint)
        many.contacted.clear()
        served = (await _rpc(http, "b1", "resources/list"))["result"]["resources"]
    assert len(resources) == 2
    truncated = [entry for entry in logs if entry["event"] == "discovery.listing_truncated"]
    assert truncated and truncated[0]["server"] == "weather"
    # the cut listing is not served, so the member is asked for all of it
    assert len(served) == 5 and many.contacted == ["weather"]


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
    """BND-8: a prompt the member's last discovery no longer listed is not served, though the
    curation cache keeps it."""
    http, upstreams = gateway
    upstreams.members["weather"] = _member(["weekly"], [])
    await http.post("/api/v1/upstreams/weather:refresh-tools")
    upstreams.contacted.clear()
    listed = (await _rpc(http, "b1", "prompts/list"))["result"]["prompts"]
    assert [p["name"] for p in listed] == ["weather__weekly"]
    assert upstreams.contacted == []
    cached = (await http.get("/api/v1/bundles/b1/member-prompts")).json()
    assert {p["key"] for p in cached} == {"daily", "weekly"}


async def test_bnd8_lists_served_from_snapshot(gateway):
    """BND-8: the three list methods answer from the stored listings without contacting the
    member, curated as the bundle says."""
    http, upstreams = gateway
    await _curate(http, "b1", "prompt", "weekly", override_title="Weekly outlook")
    upstreams.contacted.clear()
    prompts = (await _rpc(http, "b1", "prompts/list"))["result"]["prompts"]
    resources = (await _rpc(http, "b1", "resources/list"))["result"]["resources"]
    templates = (await _rpc(http, "b1", "resources/templates/list"))["result"]
    assert upstreams.contacted == []
    assert [(p["name"], p.get("title")) for p in prompts] == [
        ("weather__daily", None),
        ("weather__weekly", "Weekly outlook"),
    ]
    assert [a["name"] for a in prompts[0]["arguments"]] == ["city"]
    assert [r["uri"] for r in resources] == ["file:///a.txt", "file:///b.txt"]
    assert templates["resourceTemplates"] == []


async def test_bnd8_unshareable_member_listed_live(engine, redis):
    """BND-8, UPS-38: a member whose listing may not be shared (FastMCP marks it private) is
    asked live, with the caller's forwarded header."""
    await seed_api_key(engine, SERVICE_KEY)
    upstreams = Upstreams(crm=_member(["leads"], []))
    async with serving(engine, redis, bearer=SERVICE_KEY, client_factory=upstreams) as (http, _):
        await http.put("/api/v1/bundles/b1", json={"name": "b1"})
        crm = {
            "name": "crm",
            "url": "https://crm.example/mcp",
            "forward_headers": {"x-tenant": "x-tenant"},
        }
        await http.put("/api/v1/upstreams/crm", json=crm)
        await _discovered(http, "crm")
        await http.put("/api/v1/bundles/b1/upstreams/crm", json={"enabled": True})
        endpoint = {"name": "b1", "bundle_name": "b1", "auth_modes": ["api_key"]}
        await http.put("/api/v1/endpoints/b1", json=endpoint)
        upstreams.contacted.clear()
        upstreams.headers.clear()
        http.headers["x-tenant"] = "acme"
        listed = (await _rpc(http, "b1", "prompts/list"))["result"]["prompts"]
    assert [p["name"] for p in listed] == ["crm__leads"]
    assert "crm" in upstreams.contacted
    assert {"x-tenant": "acme"} in [
        {k: v for k, v in headers.items() if k == "x-tenant"} for headers in upstreams.headers
    ]


async def test_ups24_listing_stored_as_listed(engine, redis):
    """UPS-24, UPS-38: every page of a listing is stored, entry by entry with every field the
    server listed, in its order, and served that way because the server marked it public."""
    await seed_api_key(engine, SERVICE_KEY)
    # a server that marks its lists public is shared under the default setting
    docs = FastMCP("docs", list_page_size=1, cache_ttl=60, cache_scope="public")
    docs.resource("file:///z.csv", mime_type="text/csv", description="Zed")(_content("z"))
    docs.resource("file:///a.txt")(_content("a"))

    @docs.resource("file:///{name}.log", mime_type="text/plain")
    def log_file(name: str) -> str:
        return name

    upstreams = Upstreams(docs=docs)
    async with serving(engine, redis, bearer=SERVICE_KEY, client_factory=upstreams) as (http, _):
        await http.put("/api/v1/bundles/b1", json={"name": "b1"})
        body = {"name": "docs", "url": "https://docs.example/mcp"}
        await http.put("/api/v1/upstreams/docs", json=body)
        await _discovered(http, "docs")
        await http.put("/api/v1/bundles/b1/upstreams/docs", json={"enabled": True})
        endpoint = {"name": "b1", "bundle_name": "b1", "auth_modes": ["api_key"]}
        await http.put("/api/v1/endpoints/b1", json=endpoint)
        upstreams.contacted.clear()
        resources = (await _rpc(http, "b1", "resources/list"))["result"]["resources"]
        templates = (await _rpc(http, "b1", "resources/templates/list"))["result"]
    assert upstreams.contacted == []
    assert [(r["uri"], r.get("mimeType")) for r in resources] == [
        ("file:///z.csv", "text/csv"),
        ("file:///a.txt", "text/plain"),
    ]
    assert resources[0]["description"] == "Zed"
    assert [(t["uriTemplate"], t["mimeType"]) for t in templates["resourceTemplates"]] == [
        ("file:///{name}.log", "text/plain")
    ]


async def test_ups24_changed_listing_announced(gateway, redis):
    """UPS-24: a refresh that finds a resource the stored listing lacks announces the bundles'
    resource lists as changed."""
    http, upstreams = gateway
    upstreams.members["weather"] = _member(
        ["daily", "weekly"], ["file:///a.txt", "file:///b.txt", "file:///c.txt"]
    )
    pubsub = redis.pubsub()
    await pubsub.subscribe("bmcp:invalidate")
    # the fixture's own writes may still be publishing; only the refresh's events count
    while await pubsub.get_message(timeout=0.3) is not None:
        pass
    await http.post("/api/v1/upstreams/weather:refresh-tools")
    messages = []
    while (message := await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)):
        messages.append(message["data"])
    await pubsub.aclose()
    changed = [m for m in messages if '"entity_type":"bundle_resource"' in m]
    assert {'"key":"b1"' in m or '"key":"b2"' in m for m in changed} == {True}
    assert len(changed) == 2
    assert not any('"entity_type":"bundle_prompt"' in m for m in messages), messages


async def test_ups38_setting_round_trips(gateway):
    """UPS-38: listing_snapshot is stored, kept when omitted, and changing it probes nothing;
    under 'live' the member is asked though a listing is stored."""
    http, upstreams = gateway
    upstreams.contacted.clear()
    body = {"name": "weather", "url": "http://w/mcp", "listing_snapshot": "live"}
    written = (await http.put("/api/v1/upstreams/weather", json=body)).json()
    assert written["listing_snapshot"] == "live"
    del body["listing_snapshot"]
    await http.put("/api/v1/upstreams/weather", json=body)
    assert (await http.get("/api/v1/upstreams/weather")).json()["listing_snapshot"] == "live"
    await asyncio.sleep(0.1)
    assert upstreams.contacted == []
    await _rpc(http, "b1", "prompts/list")
    assert upstreams.contacted == ["weather"]


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


# --- concurrent live fan-out ---------------------------------------------------------------

LIVE_LISTS = {"prompts": {"listChanged": False}, "resources": {"listChanged": False}}


class Rendezvous:
    """Members whose live list call waits, with a short timeout, until every member was asked.

    Asked one after another, the first member would wait for a request that is never sent.
    """

    def __init__(self, *names: str) -> None:
        self.asked = {name: asyncio.Event() for name in names}
        self.calls: list[str] = []

    async def arrive(self, name: str) -> None:
        self.calls.append(name)
        self.asked[name].set()
        async with asyncio.timeout(1):
            for event in self.asked.values():
                await event.wait()


async def _seed_live_members(engine, *names: str) -> None:
    """Members advertising prompts and resources with no stored listing, so lists ask live."""
    await seed_api_key(engine, SERVICE_KEY)
    async with session_factory(engine)() as db:
        db.add_all(
            [
                McpServerRow(name=name, url=f"http://{name}/mcp", capabilities=LIVE_LISTS)
                for name in names
            ]
        )
        db.add(BundleRow(name="b1"))
        await db.commit()


async def _live_bundle(http, *names: str) -> None:
    for name in names:
        await http.put(f"/api/v1/bundles/b1/upstreams/{name}", json={})
    endpoint = {"name": "b1", "bundle_name": "b1", "auth_modes": ["api_key"]}
    await http.put("/api/v1/endpoints/b1", json=endpoint)


async def test_bnd38_live_members_are_asked_concurrently(engine, redis):
    """BND-38: two members that each answer prompts/list only once the other was asked are both
    listed, and each is asked once."""
    await _seed_live_members(engine, "alpha", "beta")
    members = {"alpha": _member(["morning"], []), "beta": _member(["evening"], [])}
    rendezvous = Rendezvous("alpha", "beta")

    class Gated(Client):
        member: str

        async def list_prompts(self, *args, **kwargs):
            await rendezvous.arrive(self.member)
            return await super().list_prompts(*args, **kwargs)

    def factory(server, extra_headers, *, observer=None, **handlers):
        client = Gated(members[server.name])
        client.member = server.name
        return client

    async with serving(engine, redis, bearer=SERVICE_KEY, client_factory=factory) as (http, _):
        await _live_bundle(http, "alpha", "beta")
        listed = (await _rpc(http, "b1", "prompts/list"))["result"]["prompts"]
    assert [p["name"] for p in listed] == ["alpha__morning", "beta__evening"]
    assert sorted(rendezvous.calls) == ["alpha", "beta"]


async def test_bnd38_order_holds_when_a_later_member_answers_first(engine, redis):
    """BND-38, BND-8: with zeta before alpha and alpha answering first, a URI both list is
    listed once, from zeta, and the collision is logged against alpha."""
    await _seed_live_members(engine, "zeta", "alpha")
    members = {name: FastMCP(name) for name in ("zeta", "alpha")}
    for name, member in members.items():
        member.resource("file:///a.txt", description=f"From {name}")(_content(name))
    alpha_answered = asyncio.Event()

    class Racing(Client):
        member: str

        async def list_resources(self, *args, **kwargs):
            if self.member == "zeta":
                async with asyncio.timeout(1):
                    await alpha_answered.wait()
                return await super().list_resources(*args, **kwargs)
            try:
                return await super().list_resources(*args, **kwargs)
            finally:
                alpha_answered.set()

    def factory(server, extra_headers, *, observer=None, **handlers):
        client = Racing(members[server.name])
        client.member = server.name
        return client

    async with serving(engine, redis, bearer=SERVICE_KEY, client_factory=factory) as (http, _):
        await _live_bundle(http, "zeta", "alpha")
        with capture_logs() as logs:
            listed = (await _rpc(http, "b1", "resources/list"))["result"]["resources"]
    assert [(r["uri"], r["description"]) for r in listed] == [("file:///a.txt", "From zeta")]
    collisions = [entry for entry in logs if entry["event"] == "passthrough.collision"]
    assert [(c["key"], c["server"]) for c in collisions] == [("file:///a.txt", "alpha")]


async def test_bnd38_a_failing_member_does_not_hold_back_the_others(engine, redis):
    """BND-38: one member's failing prompts/list leaves the other's prompts listed, and the
    failure is logged with its traceback."""
    await _seed_live_members(engine, "alpha", "beta")
    members = {"alpha": _member(["morning"], []), "beta": _member(["evening"], [])}

    class Failing(Client):
        member: str

        async def list_prompts(self, *args, **kwargs):
            if self.member == "alpha":
                raise RuntimeError("alpha is down")
            return await super().list_prompts(*args, **kwargs)

    def factory(server, extra_headers, *, observer=None, **handlers):
        client = Failing(members[server.name])
        client.member = server.name
        return client

    async with serving(engine, redis, bearer=SERVICE_KEY, client_factory=factory) as (http, _):
        await _live_bundle(http, "alpha", "beta")
        with capture_logs() as logs:
            listed = (await _rpc(http, "b1", "prompts/list"))["result"]["prompts"]
    assert [p["name"] for p in listed] == ["beta__evening"]
    failed = [entry for entry in logs if entry["event"] == "passthrough.member_failed"]
    assert [(f["server"], f.get("exc_info")) for f in failed] == [("alpha", True)]
