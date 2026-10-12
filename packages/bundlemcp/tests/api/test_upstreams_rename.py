"""Upstream servers are published as "upstreams" (SRV-16)."""

from httpx import AsyncClient

SERVER = {"name": "weather", "url": "http://weather/mcp"}


async def test_srv16_upstreams_are_the_published_paths(service_client: AsyncClient):
    """SRV-16: the collection and bundle membership live under /upstreams, tagged upstreams."""
    created = await service_client.put("/api/v1/upstreams/weather", json=SERVER)
    assert created.status_code == 200
    await service_client.put("/api/v1/bundles/b1", json={"name": "b1"})
    member = await service_client.put("/api/v1/bundles/b1/upstreams/weather", json={})
    assert member.status_code == 200
    members = await service_client.get("/api/v1/bundles/b1/upstreams")
    assert [m["server_name"] for m in members.json()] == ["weather"]

    schema = (await service_client.get("/api/v1/openapi.json")).json()
    assert "/api/v1/upstreams/{name}" in schema["paths"]
    assert "/api/v1/bundles/{name}/upstreams/{upstream_name}" in schema["paths"]
    tags = {t for path in schema["paths"].values() for op in path.values() for t in op["tags"]}
    assert "upstreams" in tags and "servers" not in tags


async def test_srv16_the_former_paths_are_gone(service_client: AsyncClient):
    """SRV-16: the old names are not kept as aliases."""
    await service_client.put("/api/v1/upstreams/weather", json=SERVER)
    await service_client.put("/api/v1/bundles/b1", json={"name": "b1"})
    assert (await service_client.get("/api/v1/servers/weather")).status_code == 404
    assert (await service_client.get("/api/v1/bundles/b1/servers")).status_code == 404
