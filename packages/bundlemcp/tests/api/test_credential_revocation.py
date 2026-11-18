"""Moving a server's URL through the API and the import (UPS-41, UPS-42)."""

import asyncio
import uuid

import pytest
from bundlemcp.api.oauth.session_cookie import SESSION_COOKIE
from bundlemcp.domain.sessions.admin_session import AdminSession
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.audit_record_row import AuditRecordRow
from bundlemcp.infrastructure.postgres.rows.upstream_oauth_token_row import UpstreamOAuthTokenRow
from bundlemcp.infrastructure.postgres.rows.user_row import UserRow
from cryptography.fernet import Fernet
from sqlmodel import select

from tests.conftest import SERVICE_KEY, hermetic_settings, seed_api_key, serving

SECRET = "Bearer s3cret-header-value"


@pytest.fixture
async def gateway(engine, redis):
    await seed_api_key(engine, SERVICE_KEY)
    settings = hermetic_settings(
        token_encryption_keys=[Fernet.generate_key().decode()], discovery_refresh_interval=0
    )
    async with serving(engine, redis, settings=settings, bearer=SERVICE_KEY) as (http, app):
        yield http, app


async def _put(http, name: str, body: dict) -> dict:
    resp = await http.put(f"/api/v1/upstreams/{name}", json={"name": name, **body})
    assert resp.status_code == 200, resp.text
    # the background probe shares sqlite's one connection; let it finish first
    for _ in range(100):
        if (await http.get(f"/api/v1/upstreams/{name}")).json()["connection_state"] != "unknown":
            break
        await asyncio.sleep(0.02)
    return resp.json()


async def _as_admin(http, app, engine) -> uuid.UUID:
    async with session_factory(engine)() as db:
        admin = UserRow(oidc_issuer="http://idp", oidc_sub="admin", email="a@x", is_admin=True)
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
    session_id = await app.state.container.admin_sessions.create(
        AdminSession(user_id=str(admin.id), email="a@x", is_admin=True)
    )
    http.headers.pop("Authorization")
    http.cookies.set(SESSION_COOKIE, session_id)
    return admin.id


async def test_ups41_an_admin_moving_the_url_revokes_tokens_and_is_audited(gateway, engine):
    """UPS-41: the stored tokens are gone and one management record names the admin."""
    http, app = gateway
    server = await _put(http, "seo", {"url": "http://seo/mcp", "auth_mode": "upstream_oauth"})
    async with session_factory(engine)() as db:
        db.add(
            UpstreamOAuthTokenRow(
                server_id=uuid.UUID(server["id"]), user_id=None, tokens_encrypted="shared-token"
            )
        )
        await db.commit()
    admin_id = await _as_admin(http, app, engine)

    moved = {"name": "seo", "url": "http://other/mcp", "auth_mode": "upstream_oauth"}
    origin = app.state.container.settings.public_base.rstrip("/")
    resp = await http.put("/api/v1/upstreams/seo", json=moved, headers={"Origin": origin})

    assert resp.status_code == 200, resp.text
    async with session_factory(engine)() as db:
        tokens = (await db.execute(select(UpstreamOAuthTokenRow))).scalars().all()
        records = (await db.execute(select(AuditRecordRow))).scalars().all()
    assert tokens == []
    (record,) = [r for r in records if r.kind == "management"]
    assert record.action == "upstream.credentials_revoked" and record.user_id == admin_id
    assert "shared-token" not in record.model_dump_json()


async def test_ups42_an_origin_move_without_header_values_answers_409(gateway):
    """UPS-42: the write is refused and the server keeps its URL."""
    http, _ = gateway
    await _put(http, "crm", {"url": "http://crm/mcp", "static_headers": {"Authorization": SECRET}})

    resp = await http.put("/api/v1/upstreams/crm", json={"name": "crm", "url": "http://evil/mcp"})

    assert resp.status_code == 409
    assert "UPS-42" in resp.text and SECRET not in resp.text
    assert (await http.get("/api/v1/upstreams/crm")).json()["url"] == "http://crm/mcp"


async def test_ups42_an_import_placeholder_does_not_follow_a_server_to_another_origin(gateway):
    """UPS-42: the upstream is reported as an error and keeps its URL."""
    http, _ = gateway
    await _put(http, "crm", {"url": "http://crm/mcp", "static_headers": {"Authorization": SECRET}})
    doc = {
        "upstreams": [
            {
                "name": "crm",
                "url": "http://evil/mcp",
                "static_headers": {"Authorization": {"$secret": "Authorization"}},
            }
        ]
    }

    report = (await http.post("/api/v1/import", json=doc)).json()

    (result,) = report["results"]
    assert result["outcome"] == "error" and "UPS-42" in result["message"]
    assert report["applied"] is False
    assert (await http.get("/api/v1/upstreams/crm")).json()["url"] == "http://crm/mcp"


async def test_ups42_an_import_placeholder_keeps_its_value_on_the_same_origin(gateway):
    """UPS-42: a new path on the same host may keep the stored value."""
    http, _ = gateway
    await _put(http, "crm", {"url": "http://crm/mcp", "static_headers": {"Authorization": SECRET}})
    doc = {
        "upstreams": [
            {
                "name": "crm",
                "url": "http://crm/v2/mcp",
                "static_headers": {"Authorization": {"$secret": "Authorization"}},
            }
        ]
    }

    report = (await http.post("/api/v1/import", json=doc)).json()

    assert report["applied"] is True, report
    assert (await http.get("/api/v1/upstreams/crm")).json()["url"] == "http://crm/v2/mcp"
