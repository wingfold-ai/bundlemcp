"""Tool curation through the API and the gateway: staleness, presented-name uniqueness and
member order (UPS-18, UPS-19, BND-1, BND-8, BND-14, BND-17)."""

from datetime import UTC, datetime

from bundlemcp.domain.access.api_key_kind import ApiKeyKind
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.audit_record_row import AuditRecordRow
from bundlemcp.infrastructure.postgres.rows.bundle_row import BundleRow
from bundlemcp.infrastructure.postgres.rows.bundle_tool_row import BundleToolRow
from bundlemcp.infrastructure.postgres.rows.endpoint_row import EndpointRow
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.postgres.rows.tool_row import ToolRow
from fastmcp import Client, FastMCP
from sqlmodel import select

from tests.api.test_gateway import (
    RecordingHook,
    _initialize,
    _rpc,
    _running,
    upstream_factory,
)
from tests.conftest import ENDPOINT_KEY, SERVICE_KEY, seed_api_key, serving

ADMIN = {"Authorization": f"Bearer {SERVICE_KEY}"}
EARLIER = datetime(2026, 1, 1, tzinfo=UTC)


async def _tool(app, name: str) -> ToolRow:
    async with app.state.container.session_factory() as db:
        return (await db.execute(select(ToolRow).where(ToolRow.name == name))).scalar_one()


async def _mark_stale(app, name: str) -> None:
    async with app.state.container.session_factory() as db:
        row = (await db.execute(select(ToolRow).where(ToolRow.name == name))).scalar_one()
        row.stale_since = EARLIER
        db.add(row)
        await db.commit()


async def _curate(app, tool_name: str, **fields) -> None:
    async with app.state.container.session_factory() as db:
        bundle = (await db.execute(select(BundleRow))).scalar_one()
        tool = (await db.execute(select(ToolRow).where(ToolRow.name == tool_name))).scalar_one()
        db.add(BundleToolRow(bundle_id=bundle.id, tool_id=tool.id, **fields))
        await db.commit()


async def _listed(http, endpoint: str = "main") -> set[str]:
    session = await _initialize(http, endpoint)
    listing = await _rpc(http, endpoint, session, "tools/list")
    return {t["name"] for t in listing.json()["result"]["tools"]}


# --- staleness ---------------------------------------------------------------------------


async def test_ups19_stale_tool_not_listed_and_rejected_on_call(engine, redis):
    """UPS-19/PROT-25: a stale tool is absent from tools/list, and a call to it is rejected as
    an unknown tool, audited as denied, without metering or contacting the upstream."""
    contacted: list[str] = []

    def recording_factory(server, extra_headers, **handlers):
        contacted.append(server.name)
        return upstream_factory(server, extra_headers, **handlers)

    hook = RecordingHook()
    async with _running(engine, redis, client_factory=recording_factory, metering_hook=hook) as (
        http,
        app,
    ):
        await _mark_stale(app, "say")
        assert "echo__say" not in await _listed(http)

        session = await _initialize(http)
        call = await _rpc(
            http, "main", session, "tools/call", {"name": "echo__say", "arguments": {"text": "x"}}
        )
        assert "Unknown tool" in call.json()["error"]["message"]
        await app.state.container.audit.drain()
        async with app.state.container.session_factory() as db:
            records = (await db.execute(select(AuditRecordRow))).scalars().all()
    assert [(r.status, r.denied_reason) for r in records] == [
        ("denied", "unknown_or_disabled_tool")
    ]
    assert contacted == []
    assert hook.pre_calls == []


async def test_ups19_vanished_tool_goes_stale_and_keeps_curation(engine, redis):
    """UPS-19: a tool the upstream stops listing stays cached with its curation, is reported
    stale, and is no longer served; the run counts it as a change."""
    await seed_api_key(engine, SERVICE_KEY)
    async with _running(engine, redis) as (http, app):
        echo = await _tool(app, "say")
        async with app.state.container.session_factory() as db:
            db.add(ToolRow(server_id=echo.server_id, name="gone", schema_hash="h"))
            await db.commit()
        await _curate(app, "gone", override_title="Gone")

        refreshed = await http.post("/api/v1/upstreams/echo:refresh-tools", headers=ADMIN)
        assert refreshed.json()["error"] is None
        assert refreshed.json()["changed"] >= 1

        tools = (await http.get("/api/v1/bundles/main/tools", headers=ADMIN)).json()
        gone = next(t for t in tools if t["name"] == "gone")
        assert gone["stale"] is True
        assert gone["override_title"] == "Gone"
        upstream = (await http.get("/api/v1/upstreams/echo/tools", headers=ADMIN)).json()
        assert {t["name"]: t["stale"] for t in upstream["items"]}["gone"] is True
        assert "echo__gone" not in await _listed(http)


async def test_ups19_reappearing_tool_keeps_curation(engine, redis):
    """UPS-19: a stale tool that a later discovery lists again is served with its curation."""
    await seed_api_key(engine, SERVICE_KEY)
    async with _running(engine, redis) as (http, app):
        await _mark_stale(app, "say")
        await _curate(app, "say", override_name="b")
        assert "b" not in await _listed(http)

        await http.post("/api/v1/upstreams/echo:refresh-tools", headers=ADMIN)

        assert (await _tool(app, "say")).stale_since is None
        assert "b" in await _listed(http)


async def test_ups18_unchanged_run_writes_no_tool(engine, redis):
    """UPS-18: a discovery that lists exactly what is cached writes no tool and reports no
    change."""
    await seed_api_key(engine, SERVICE_KEY)
    async with _running(engine, redis) as (http, app):
        await http.post("/api/v1/upstreams/echo:refresh-tools", headers=ADMIN)
        before = {
            t.name: t.schema_hash for t in [await _tool(app, "say"), await _tool(app, "fail")]
        }

        again = await http.post("/api/v1/upstreams/echo:refresh-tools", headers=ADMIN)

        assert again.json()["changed"] == 0
        after = {t.name: t.schema_hash for t in [await _tool(app, "say"), await _tool(app, "fail")]}
        assert after == before


async def test_ups19_refresh_and_prune_deletes_stale_tools(engine, redis):
    """UPS-19: refresh & prune deletes the server's stale tools and their curation."""
    await seed_api_key(engine, SERVICE_KEY)
    async with _running(engine, redis) as (http, app):
        echo = await _tool(app, "say")
        async with app.state.container.session_factory() as db:
            db.add(ToolRow(server_id=echo.server_id, name="beta", schema_hash="h"))
            await db.commit()
        await _curate(app, "beta", override_name="b")

        pruned = await http.post("/api/v1/upstreams/echo:refresh-tools?prune=true", headers=ADMIN)

        assert pruned.json()["pruned"] == 1
        async with app.state.container.session_factory() as db:
            names = {t.name for t in (await db.execute(select(ToolRow))).scalars()}
            curations = (await db.execute(select(BundleToolRow))).scalars().all()
        assert "beta" not in names and {"say", "fail"} <= names
        assert curations == []


async def test_ups19_prune_after_failed_probe_deletes_nothing(engine, redis):
    """UPS-19: a refresh & prune whose probe fails reports the failure and deletes nothing."""

    def failing(server, extra_headers, **handlers):
        raise ConnectionError("upstream down")

    await seed_api_key(engine, SERVICE_KEY)
    async with _running(engine, redis, client_factory=failing) as (http, app):
        await _mark_stale(app, "say")

        pruned = await http.post("/api/v1/upstreams/echo:refresh-tools?prune=true", headers=ADMIN)

        assert pruned.json()["error"] is not None
        assert pruned.json()["pruned"] == 0
        assert (await _tool(app, "say")).stale_since is not None


async def test_bnd17_staleness_listed(engine, redis):
    """BND-17: the curation listing reports stale: true for a stale tool only, and the
    catalogue leaves it out."""
    await seed_api_key(engine, SERVICE_KEY)
    async with _running(engine, redis) as (http, app):
        await _mark_stale(app, "fail")
        tools = (await http.get("/api/v1/bundles/main/tools", headers=ADMIN)).json()
        assert {t["name"]: t["stale"] for t in tools} == {
            "say": False,
            "fail": True,
            "write_note": False,
        }


async def test_bnd17_annotation_overrides_listed(engine, redis):
    """BND-17: an annotation override written through the API is listed back."""
    await seed_api_key(engine, SERVICE_KEY)
    async with _running(engine, redis) as (http, app):
        say = await _tool(app, "say")
        put = await http.put(
            f"/api/v1/bundles/main/tools/{say.id}",
            headers=ADMIN,
            json={"enabled": True, "override_annotations": {"readOnlyHint": True}},
        )
        assert put.status_code == 200, put.text
        tools = (await http.get("/api/v1/bundles/main/tools", headers=ADMIN)).json()
        listed = next(t for t in tools if t["name"] == "say")
        assert listed["override_annotations"] == {"readOnlyHint": True}


# --- presented names ---------------------------------------------------------------------


async def test_bnd14_override_equal_to_prefixed_name_conflicts(engine, redis):
    """BND-14: an override name equal to another tool's prefixed name is refused with 409
    naming the colliding tool."""
    await seed_api_key(engine, SERVICE_KEY)
    async with _running(engine, redis) as (http, app):
        note = await _tool(app, "write_note")
        put = await http.put(
            f"/api/v1/bundles/main/tools/{note.id}",
            headers=ADMIN,
            json={"enabled": True, "override_name": "echo__say"},
        )
        assert put.status_code == 409
        assert "echo/say" in put.json()["detail"]


async def test_bnd14_override_equal_to_own_prefixed_name_allowed(engine, redis):
    """BND-14: a tool may carry its own prefixed name as its override."""
    await seed_api_key(engine, SERVICE_KEY)
    async with _running(engine, redis) as (http, app):
        say = await _tool(app, "say")
        put = await http.put(
            f"/api/v1/bundles/main/tools/{say.id}",
            headers=ADMIN,
            json={"enabled": True, "override_name": "echo__say"},
        )
        assert put.status_code == 200, put.text


async def test_bnd14_member_add_collision_conflicts(engine, redis):
    """BND-14: adding a member whose prefixed name equals an existing override is refused,
    and the members are unchanged."""
    await seed_api_key(engine, SERVICE_KEY)
    async with _running(engine, redis) as (http, app):
        await http.delete("/api/v1/bundles/main/upstreams/notes", headers=ADMIN)
        await _curate(app, "say", override_name="notes__write_note")

        put = await http.put("/api/v1/bundles/main/upstreams/notes", headers=ADMIN, json={})

        assert put.status_code == 409
        members = (await http.get("/api/v1/bundles/main/upstreams", headers=ADMIN)).json()
        assert [m["server_name"] for m in members] == ["echo"]


async def test_bnd14_rename_into_collision_conflicts(engine, redis):
    """BND-14: renaming a member upstream so that one of its prefixed names equals an
    override is refused with 409 naming the bundle."""
    await seed_api_key(engine, SERVICE_KEY)
    async with _running(engine, redis) as (http, app):
        await _curate(app, "say", override_name="memo__write_note")

        renamed = await http.post(
            "/api/v1/upstreams/notes:rename?new_name=memo&force=true", headers=ADMIN
        )

        assert renamed.status_code == 409
        assert "'main'" in renamed.json()["detail"]
        assert (await http.get("/api/v1/upstreams/notes", headers=ADMIN)).status_code == 200


async def test_bnd14_discovered_collision_keeps_override(engine, redis):
    """BND-14: when discovery brings a tool whose prefixed name equals an override, the
    override keeps the name and the discovered tool is not served under it."""
    async with _running(engine, redis) as (http, app):
        await _curate(app, "say", override_name="notes__write_note")

        session = await _initialize(http)
        listing = await _rpc(http, "main", session, "tools/list")
        names = [t["name"] for t in listing.json()["result"]["tools"]]
        assert names.count("notes__write_note") == 1
        call = await _rpc(
            http,
            "main",
            session,
            "tools/call",
            {"name": "notes__write_note", "arguments": {"text": "z"}},
        )
        assert call.json()["result"]["content"][0]["text"] == "echo:z"


# --- member order ------------------------------------------------------------------------

zeta = FastMCP("zeta")
alpha = FastMCP("alpha")


@zeta.resource("file:///a.txt")
def zeta_a() -> str:
    return "from zeta"


@alpha.resource("file:///a.txt")
def alpha_a() -> str:
    return "from alpha"


ORDERED = {"zeta": zeta, "alpha": alpha}
RESOURCES = {"resources": {"subscribe": False, "listChanged": False}}


def ordered_factory(server, extra_headers, *, observer=None, **handlers):
    return Client(ORDERED[server.name])


async def _seed_ordered(engine) -> None:
    """Upstreams zeta and alpha, both listing file:///a.txt, and a bundle with no members."""
    await seed_api_key(engine, SERVICE_KEY)
    await seed_api_key(engine, ENDPOINT_KEY, name="ep", kind=ApiKeyKind.ENDPOINT)
    async with session_factory(engine)() as db:
        bundle = BundleRow(name="main", description="ordered")
        db.add_all(
            [
                McpServerRow(name="zeta", url="http://zeta/mcp", capabilities=RESOURCES),
                McpServerRow(name="alpha", url="http://alpha/mcp", capabilities=RESOURCES),
                bundle,
            ]
        )
        await db.commit()
        await db.refresh(bundle)
        db.add(EndpointRow(name="main", bundle_id=bundle.id, auth_modes=["api_key"]))
        await db.commit()


async def _members(http) -> list[str]:
    members = (await http.get("/api/v1/bundles/main/upstreams", headers=ADMIN)).json()
    return [m["server_name"] for m in members]


async def test_bnd1_members_listed_in_member_order(engine, redis):
    """BND-1: members are listed in the order they were added, not by name."""
    await _seed_ordered(engine)
    async with serving(engine, redis, client_factory=ordered_factory) as (http, _app):
        for name in ("zeta", "alpha"):
            await http.put(f"/api/v1/bundles/main/upstreams/{name}", headers=ADMIN, json={})
        assert await _members(http) == ["zeta", "alpha"]


async def test_bnd1_reorder(engine, redis):
    """BND-1: an admin reorders the members with the whole list."""
    await _seed_ordered(engine)
    async with serving(engine, redis, client_factory=ordered_factory) as (http, _app):
        for name in ("zeta", "alpha"):
            await http.put(f"/api/v1/bundles/main/upstreams/{name}", headers=ADMIN, json={})

        put = await http.put(
            "/api/v1/bundles/main/upstreams:order",
            headers=ADMIN,
            json={"upstreams": ["alpha", "zeta"]},
        )

        assert put.status_code == 200, put.text
        assert [m["server_name"] for m in put.json()] == ["alpha", "zeta"]
        assert await _members(http) == ["alpha", "zeta"]


async def test_bnd1_reorder_must_be_permutation(engine, redis):
    """BND-1: a reorder that omits, repeats or adds a member is refused with 422 and the
    order is unchanged."""
    await _seed_ordered(engine)
    async with serving(engine, redis, client_factory=ordered_factory) as (http, _app):
        for name in ("zeta", "alpha"):
            await http.put(f"/api/v1/bundles/main/upstreams/{name}", headers=ADMIN, json={})

        for wrong in (["alpha"], ["alpha", "alpha", "zeta"], ["alpha", "zeta", "nosuch"]):
            put = await http.put(
                "/api/v1/bundles/main/upstreams:order", headers=ADMIN, json={"upstreams": wrong}
            )
            assert put.status_code == 422, wrong

        assert await _members(http) == ["zeta", "alpha"]


async def test_bnd8_first_member_in_member_order_wins_uri_collision(engine, redis):
    """BND-8: with zeta ordered before alpha, a URI both list is listed once and read from
    zeta; after a reorder alpha answers."""
    await _seed_ordered(engine)
    async with serving(engine, redis, client_factory=ordered_factory, bearer=ENDPOINT_KEY) as (
        http,
        _app,
    ):
        for name in ("zeta", "alpha"):
            await http.put(f"/api/v1/bundles/main/upstreams/{name}", headers=ADMIN, json={})

        session = await _initialize(http)
        listing = await _rpc(http, "main", session, "resources/list")
        assert [r["uri"] for r in listing.json()["result"]["resources"]] == ["file:///a.txt"]
        read = await _rpc(http, "main", session, "resources/read", {"uri": "file:///a.txt"})
        assert read.json()["result"]["contents"][0]["text"] == "from zeta"

        await http.put(
            "/api/v1/bundles/main/upstreams:order",
            headers=ADMIN,
            json={"upstreams": ["alpha", "zeta"]},
        )
        read = await _rpc(http, "main", session, "resources/read", {"uri": "file:///a.txt"})
        assert read.json()["result"]["contents"][0]["text"] == "from alpha"
