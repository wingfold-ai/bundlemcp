"""Audit-records listing API (AUD-6: filters + API-5 pagination)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from bundlemcp.api.app import create_app
from bundlemcp.models import ApiKey, ApiKeyKind, AuditRecord
from bundlemcp.security import API_KEY_PREFIX, display_prefix, generate_token, hash_token
from bundlemcp.settings import Settings
from bundlemcp.store import session_factory
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

SERVICE_KEY = generate_token(API_KEY_PREFIX)


@pytest.fixture
async def client(engine: AsyncEngine, redis: FakeRedis) -> AsyncIterator[AsyncClient]:
    settings = Settings(_env_file=None, database_url="sqlite+aiosqlite://")
    app = create_app(settings, engine=engine, redis=redis)

    factory = session_factory(engine)
    async with factory() as db:
        db.add(
            ApiKey(
                name="test-service",
                key_hash=hash_token(SERVICE_KEY),
                key_prefix=display_prefix(SERVICE_KEY),
                kind=ApiKeyKind.SERVICE,
            )
        )
        db.add(
            AuditRecord(
                created_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
                endpoint_name="demo",
                bundle_name="demo",
                server_name="echo",
                tool_name="echo",
                presented_tool_name="echo__echo",
                status="success",
                duration_ms=12,
            )
        )
        db.add(
            AuditRecord(
                created_at=datetime(2026, 7, 2, 10, 0, tzinfo=UTC),
                endpoint_name="seo",
                bundle_name="seo",
                server_name="seo-gsc",
                tool_name="list_sites",
                presented_tool_name="seo-gsc__list_sites",
                status="denied",
                denied_reason="tool disabled",
            )
        )
        await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {SERVICE_KEY}"},
    ) as c:
        async with app.router.lifespan_context(app):
            yield c


async def test_list_audit_records_paged(client: AsyncClient):
    """AUD-6/API-5: paginated list, newest first."""
    resp = await client.get("/api/v1/audit-records")
    assert resp.status_code == 200
    page = resp.json()
    assert page["total"] == 2
    assert [r["endpoint_name"] for r in page["items"]] == ["seo", "demo"]


async def test_audit_filters(client: AsyncClient):
    """AUD-6: endpoint/status/tool/time filters narrow the result."""
    by_status = (await client.get("/api/v1/audit-records", params={"status": "denied"})).json()
    assert by_status["total"] == 1
    assert by_status["items"][0]["denied_reason"] == "tool disabled"

    by_tool = (
        await client.get("/api/v1/audit-records", params={"tool_name": "seo-gsc__list_sites"})
    ).json()
    assert by_tool["total"] == 1  # matches the presented name too

    windowed = (
        await client.get(
            "/api/v1/audit-records",
            params={"created_from": "2026-07-01T00:00:00Z", "created_to": "2026-07-01T23:59:59Z"},
        )
    ).json()
    assert windowed["total"] == 1
    assert windowed["items"][0]["endpoint_name"] == "demo"


async def test_audit_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/audit-records", headers={"Authorization": ""})
    assert resp.status_code == 401
