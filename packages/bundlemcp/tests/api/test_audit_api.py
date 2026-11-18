"""Audit-records listing API (OPS-6: filters + MGMT-5 pagination)."""

from datetime import UTC, datetime

import pytest
from bundlemcp.domain.shared.secrets import API_KEY_PREFIX, generate_token
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.audit_record_row import AuditRecordRow
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

SERVICE_KEY = generate_token(API_KEY_PREFIX)


@pytest.fixture
async def client(service_client: AsyncClient, engine: AsyncEngine) -> AsyncClient:
    async with session_factory(engine)() as db:
        db.add(
            AuditRecordRow(
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
            AuditRecordRow(
                created_at=datetime(2026, 7, 2, 10, 0, tzinfo=UTC),
                endpoint_name="seo",
                bundle_name="seo",
                server_name="crm",
                tool_name="list_sites",
                presented_tool_name="crm__list_sites",
                status="denied",
                denied_reason="tool disabled",
            )
        )
        await db.commit()
    return service_client


async def test_list_audit_records_paged(client: AsyncClient):
    """OPS-6/MGMT-5: paginated list, newest first."""
    resp = await client.get("/api/v1/audit-records")
    assert resp.status_code == 200
    page = resp.json()
    assert page["total"] == 2
    assert [r["endpoint_name"] for r in page["items"]] == ["seo", "demo"]


async def test_audit_filters(client: AsyncClient):
    """OPS-6: endpoint/status/tool/time filters narrow the result."""
    by_status = (await client.get("/api/v1/audit-records", params={"status": "denied"})).json()
    assert by_status["total"] == 1
    assert by_status["items"][0]["denied_reason"] == "tool disabled"

    by_tool = (
        await client.get("/api/v1/audit-records", params={"tool_name": "crm__list_sites"})
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
