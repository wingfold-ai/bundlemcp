"""The servers → upstreams rename of the management API (SRV-16) and its old paths (API-8)."""

from datetime import UTC, datetime

from bundlemcp.application.contracts.live_state.counters import DEPRECATED_ROUTE_REQUESTS
from fakeredis.aioredis import FakeRedis
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from structlog.testing import capture_logs

from tests.conftest import SERVICE_KEY, seed_api_key, serving

SERVER = {"name": "weather", "url": "http://weather/mcp"}


class PinnedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


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


async def test_api8_old_paths_answer_identically_and_say_where_to_go(
    service_client: AsyncClient,
):
    """API-8: an old path behaves like the new one and says it is deprecated, until when, and
    where it moved."""
    await service_client.put("/api/v1/upstreams/weather", json=SERVER)
    new = await service_client.get("/api/v1/upstreams/weather")
    old = await service_client.get("/api/v1/servers/weather")
    assert old.status_code == 200
    assert old.json() == new.json()
    assert old.headers["deprecation"] == "@1791763200"
    assert old.headers["sunset"] == "Sat, 10 Apr 2027 00:00:00 GMT"
    assert old.headers["link"] == '</api/v1/upstreams/weather>; rel="successor-version"'
    assert "deprecation" not in new.headers


async def test_api8_bundle_member_alias_fills_in_the_successor(service_client: AsyncClient):
    """API-8: a bundle membership route moved on its own also keeps answering at the old path."""
    await service_client.put("/api/v1/upstreams/weather", json=SERVER)
    await service_client.put("/api/v1/bundles/b1", json={"name": "b1"})
    old = await service_client.put("/api/v1/bundles/b1/servers/weather", json={})
    assert old.status_code == 200
    assert old.headers["link"] == '</api/v1/bundles/b1/upstreams/weather>; rel="successor-version"'
    removed = await service_client.delete("/api/v1/bundles/b1/servers/weather")
    assert removed.status_code == 204
    assert "sunset" in removed.headers


async def test_api8_headers_are_on_error_responses_too(service_client: AsyncClient):
    """API-8: a request refused before the route runs still learns that the path moved."""
    refused = await service_client.get("/api/v1/servers", headers={"Authorization": ""})
    assert refused.status_code == 401
    assert refused.headers["link"] == '</api/v1/upstreams>; rel="successor-version"'
    missing = await service_client.get("/api/v1/servers/nope")
    assert missing.status_code == 404
    assert "deprecation" in missing.headers


async def test_api8_old_paths_are_not_in_the_openapi_document(service_client: AsyncClient):
    """API-8: generated clients only learn the new paths."""
    schema = (await service_client.get("/api/v1/openapi.json")).json()
    assert not [path for path in schema["paths"] if "/servers" in path]


async def test_api8_each_use_is_counted_and_warned_once_per_caller(
    engine: AsyncEngine, redis: FakeRedis
):
    """API-8: every use counts per old path; the warning names the caller once an hour."""
    await seed_api_key(engine, SERVICE_KEY)
    async with serving(engine, redis, bearer=SERVICE_KEY) as (http, app):
        with capture_logs() as logs:
            for _ in range(3):
                assert (await http.get("/api/v1/servers")).status_code == 200
        counters = app.state.container.counters
        assert counters.get(f"{DEPRECATED_ROUTE_REQUESTS}:/api/v1/servers") == 3
    warnings = [entry for entry in logs if entry["event"] == "api.deprecated_route"]
    assert len(warnings) == 1
    assert warnings[0]["successor"] == "/api/v1/upstreams"
    assert warnings[0]["caller"].startswith("api_key:")


async def test_api8_old_paths_are_gone_after_the_sunset(engine: AsyncEngine, redis: FakeRedis):
    """API-8: past the sunset date an old path answers 410 and names the new one."""
    await seed_api_key(engine, SERVICE_KEY)
    after_sunset = PinnedClock(datetime(2027, 4, 10, 9, tzinfo=UTC))
    async with serving(engine, redis, bearer=SERVICE_KEY, clock=after_sunset) as (http, _app):
        gone = await http.get("/api/v1/servers")
        assert gone.status_code == 410
        assert "/api/v1/upstreams" in gone.json()["detail"]
        assert (await http.get("/api/v1/upstreams")).status_code == 200
