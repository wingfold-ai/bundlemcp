"""The handshake-only protocol mode is named 'session'; 'legacy' is an input alias (UPS-10)."""

from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from httpx import AsyncClient
from sqlmodel import select

SERVER = {"name": "weather", "url": "http://weather/mcp"}


async def _stored_mode(engine, name: str) -> str:
    async with session_factory(engine)() as db:
        row = (await db.execute(select(McpServerRow).where(McpServerRow.name == name))).scalar_one()
        return row.protocol_mode


async def test_ups10_legacy_alias_is_stored_and_read_as_session(
    service_client: AsyncClient, engine
):
    """UPS-10: a write with the deprecated 'legacy' succeeds, the response and every later read
    say 'session', and the row keeps the spelling the previous release reads."""
    written = await service_client.put(
        "/api/v1/upstreams/weather", json={**SERVER, "protocol_mode": "legacy"}
    )
    assert written.status_code == 200
    assert written.json()["protocol_mode"] == "session"
    read = await service_client.get("/api/v1/upstreams/weather")
    assert read.json()["protocol_mode"] == "session"
    listed = await service_client.get("/api/v1/upstreams")
    assert [s["protocol_mode"] for s in listed.json()["items"]] == ["session"]
    assert await _stored_mode(engine, "weather") == "legacy"


async def test_ups10_omitted_mode_is_kept_on_update(service_client: AsyncClient):
    """UPS-10: an update without protocol_mode keeps 'session'."""
    await service_client.put(
        "/api/v1/upstreams/weather", json={**SERVER, "protocol_mode": "session"}
    )
    updated = await service_client.put("/api/v1/upstreams/weather", json=SERVER)
    assert updated.json()["protocol_mode"] == "session"


async def test_ups10_invalid_mode_is_rejected(service_client: AsyncClient):
    """UPS-10: a mode that is neither named nor a revision date is answered with 422."""
    for mode in ("newest", "2026-7-28"):
        resp = await service_client.put(
            "/api/v1/upstreams/weather", json={**SERVER, "protocol_mode": mode}
        )
        assert resp.status_code == 422, mode


async def test_ups10_server_stored_before_the_rename_reads_as_session(
    service_client: AsyncClient, engine
):
    """UPS-10: a server an earlier release stored as 'legacy' is read and exported as 'session'."""
    async with session_factory(engine)() as db:
        db.add(McpServerRow(name="old", url="http://old/mcp", protocol_mode="legacy"))
        await db.commit()
    read = await service_client.get("/api/v1/upstreams/old")
    assert read.json()["protocol_mode"] == "session"
    exported = (await service_client.get("/api/v1/export")).json()
    (upstream,) = [u for u in exported["upstreams"] if u["name"] == "old"]
    assert upstream["protocol_mode"] == "session"


async def test_ups10_openapi_lists_named_modes_as_an_enum(service_client: AsyncClient):
    """UPS-10: on the write and read schemas, protocol_mode offers 'auto' and 'session' as an
    enum beside the revision-date pattern, and does not list 'legacy'."""
    schema = (await service_client.get("/api/v1/openapi.json")).json()
    schemas = schema["components"]["schemas"]

    def resolve(node: dict) -> dict:
        ref = node.get("$ref")
        return schemas[ref.rsplit("/", 1)[-1]] if ref else node

    for model in ("ServerUpsert", "ServerRead"):
        options = [resolve(o) for o in _flattened(schemas[model]["properties"]["protocol_mode"])]
        enums = [o["enum"] for o in options if "enum" in o]
        patterns = [o["pattern"] for o in options if "pattern" in o]
        assert enums == [["auto", "session"]], model
        assert patterns == [r"^\d{4}-\d{2}-\d{2}$"], model
        assert "legacy" not in str(options)


def _flattened(node: dict) -> list[dict]:
    """The leaf alternatives of a schema's anyOf, with nested unions and null dropped."""
    if "anyOf" not in node:
        return [] if node.get("type") == "null" else [node]
    return [leaf for option in node["anyOf"] for leaf in _flattened(option)]
