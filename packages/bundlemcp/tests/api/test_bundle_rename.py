"""Renaming a bundle through the management API (BND-10)."""

from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.postgres.rows.tool_row import ToolRow
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select


async def _composed(http: AsyncClient, engine: AsyncEngine) -> dict:
    """Bundle b1 with member weather, a curated tool and endpoint b1-api."""
    await http.put("/api/v1/upstreams/weather", json={"name": "weather", "url": "http://w/mcp"})
    bundle = (await http.put("/api/v1/bundles/b1", json={"name": "b1"})).json()
    assert (await http.put("/api/v1/bundles/b1/upstreams/weather", json={})).status_code == 200
    async with session_factory(engine)() as db:
        server = (
            await db.execute(select(McpServerRow).where(McpServerRow.name == "weather"))
        ).scalar_one()
        tool = ToolRow(server_id=server.id, name="forecast", schema_hash="h")
        db.add(tool)
        await db.commit()
        tool_id = tool.id
    curated = await http.put(
        f"/api/v1/bundles/b1/tools/{tool_id}",
        json={"enabled": True, "override_title": "Forecast"},
    )
    assert curated.status_code == 200, curated.text
    endpoint = await http.put(
        "/api/v1/endpoints/b1-api",
        json={"name": "b1-api", "bundle_name": "b1", "auth_modes": ["api_key"]},
    )
    assert endpoint.status_code == 200, endpoint.text
    return bundle


async def test_bnd10_rename_without_force_is_refused(service_client: AsyncClient):
    """BND-10: without force the rename is refused with 409 naming the consequence for
    documents keyed on the old name, and nothing is renamed."""
    await service_client.put("/api/v1/bundles/b1", json={"name": "b1"})

    refused = await service_client.post("/api/v1/bundles/b1:rename?new_name=b2")

    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert "'b1'" in detail and "new bundle" in detail and "force=true" in detail
    assert (await service_client.get("/api/v1/bundles/b1")).status_code == 200
    assert (await service_client.get("/api/v1/bundles/b2")).status_code == 404


async def test_bnd10_acknowledged_rename_keeps_the_bundle(
    service_client: AsyncClient, engine: AsyncEngine
):
    """BND-10: an acknowledged rename keeps the bundle's id, members, curation and endpoint;
    the endpoint now serves the bundle under its new name."""
    before = await _composed(service_client, engine)

    renamed = await service_client.post("/api/v1/bundles/b1:rename?new_name=b2&force=true")

    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "b2"
    assert renamed.json()["id"] == before["id"]
    assert (await service_client.get("/api/v1/bundles/b1")).status_code == 404
    members = (await service_client.get("/api/v1/bundles/b2/upstreams")).json()
    assert [m["server_name"] for m in members] == ["weather"]
    tools = (await service_client.get("/api/v1/bundles/b2/tools")).json()
    assert [(t["name"], t["override_title"]) for t in tools] == [("forecast", "Forecast")]
    endpoint = (await service_client.get("/api/v1/endpoints/b1-api")).json()
    assert endpoint["bundle_id"] == before["id"]


async def test_bnd10_rename_onto_a_taken_name_conflicts(service_client: AsyncClient):
    """BND-10: renaming onto another bundle's name is refused with 409 and neither bundle
    changes."""
    first = (await service_client.put("/api/v1/bundles/b1", json={"name": "b1"})).json()
    second = (
        await service_client.put("/api/v1/bundles/b2", json={"name": "b2", "description": "two"})
    ).json()

    refused = await service_client.post("/api/v1/bundles/b1:rename?new_name=b2&force=true")

    assert refused.status_code == 409
    assert "'b2'" in refused.json()["detail"]
    assert (await service_client.get("/api/v1/bundles/b1")).json()["id"] == first["id"]
    still = (await service_client.get("/api/v1/bundles/b2")).json()
    assert still["id"] == second["id"] and still["description"] == "two"


async def test_bnd10_rename_validates_the_new_name(service_client: AsyncClient):
    """BND-10: a new name that is not a valid resource name is rejected and nothing changes."""
    await service_client.put("/api/v1/bundles/b1", json={"name": "b1"})

    rejected = await service_client.post(
        "/api/v1/bundles/b1:rename?new_name=no%20spaces&force=true"
    )

    assert rejected.status_code == 422
    assert (await service_client.get("/api/v1/bundles/b1")).status_code == 200
