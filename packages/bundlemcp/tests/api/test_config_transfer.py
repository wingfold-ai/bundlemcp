"""Exporting the configuration and importing it again (MGMT-17..21, SEC-11, OPS-18, BND-10/32)."""

import json
import uuid

import pytest
from bundlemcp.api.oauth.session_cookie import SESSION_COOKIE
from bundlemcp.application.bootstrap.bootstrap_document import BootstrapDocument
from bundlemcp.domain.sessions.admin_session import AdminSession
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.audit_record_row import AuditRecordRow
from bundlemcp.infrastructure.postgres.rows.tool_row import ToolRow
from bundlemcp.infrastructure.postgres.rows.user_row import UserRow
from cryptography.fernet import Fernet
from sqlmodel import select

from tests.conftest import SERVICE_KEY, hermetic_settings, seed_api_key, serving

SECRET = "Bearer s3cret-header-value"
CLIENT_SECRET = "oauth-client-s3cret"


def _settings():
    return hermetic_settings(
        token_encryption_keys=[Fernet.generate_key().decode()], discovery_refresh_interval=0
    )


@pytest.fixture
async def gateway(engine, redis):
    await seed_api_key(engine, SERVICE_KEY)
    async with serving(engine, redis, settings=_settings(), bearer=SERVICE_KEY) as (http, app):
        yield http, app


async def _configure(http, engine) -> None:
    """Upstream weather with a secret header and OAuth client, bundle b1 curated, endpoint."""
    weather = {
        "name": "weather",
        "url": "http://weather/mcp",
        "static_headers": {"Authorization": SECRET},
    }
    assert (await http.put("/api/v1/upstreams/weather", json=weather)).status_code == 200
    oauth = {"client_id": "gw", "client_secret": CLIENT_SECRET}
    resp = await http.put("/api/v1/upstreams/weather/upstream-oauth", json=oauth)
    assert resp.status_code == 200, resp.text
    weather_row = (await http.get("/api/v1/upstreams/weather")).json()
    async with session_factory(engine)() as db:
        db.add(
            ToolRow(
                server_id=uuid.UUID(weather_row["id"]),
                name="forecast",
                schema_hash="h",
                input_schema={},
            )
        )
        await db.commit()
    await http.put("/api/v1/bundles/b1", json={"name": "b1", "description": "first"})
    await http.put("/api/v1/bundles/b1/upstreams/weather", json={"enabled": False})
    tools = (await http.get("/api/v1/bundles/b1/tools")).json()
    forecast = next(t for t in tools if t["name"] == "forecast")
    curated = {"enabled": True, "override_title": "Forecast"}
    resp = await http.put(f"/api/v1/bundles/b1/tools/{forecast['tool_id']}", json=curated)
    assert resp.status_code == 200, resp.text
    resource = {"name": "handbook", "content": "# Handbook"}
    assert (await http.put("/api/v1/bundles/b1/resources/handbook", json=resource)).is_success
    endpoint = {"name": "b1-api", "bundle_name": "b1", "auth_modes": ["api_key"]}
    assert (await http.put("/api/v1/endpoints/b1-api", json=endpoint)).status_code == 200


async def test_mgmt17_export_lists_every_resource_by_name(gateway, engine):
    """MGMT-17, UPS-16, BND-32: the document names every resource, and bootstrap accepts it."""
    http, _ = gateway
    await _configure(http, engine)
    resp = await http.get("/api/v1/export")
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["version"] == 1 and "servers" not in doc
    assert [u["name"] for u in doc["upstreams"]] == ["weather"]
    (b1,) = doc["bundles"]
    assert b1["upstreams"] == [
        {
            "name": "weather",
            "enabled": False,
            "tools": [
                {
                    "tool": "forecast",
                    "enabled": True,
                    "override_title": "Forecast",
                }
            ],
        }
    ]
    assert [r["name"] for r in b1["resources"]] == ["handbook"]
    assert b1["resources"][0]["content"] == "# Handbook"
    assert [e["name"] for e in doc["endpoints"]] == ["b1-api"]
    assert "id" not in json.dumps(doc["endpoints"])
    BootstrapDocument.model_validate(doc)


async def test_mgmt18_default_export_withholds_secrets(gateway, engine):
    """MGMT-18, SEC-11: placeholders instead of values, and no warning."""
    http, _ = gateway
    await _configure(http, engine)
    doc = (await http.get("/api/v1/export")).json()
    assert doc["upstreams"][0]["static_headers"] == {"Authorization": {"$secret": "Authorization"}}
    assert doc["upstreams"][0]["upstream_oauth"]["client_secret"] == {"$secret": "client_secret"}
    body = json.dumps(doc)
    assert SECRET not in body and CLIENT_SECRET not in body
    assert "warning" not in doc


async def test_mgmt19_export_then_import_changes_nothing(gateway, engine):
    """MGMT-18, MGMT-19: re-importing an export on the same instance skips every resource."""
    http, _ = gateway
    await _configure(http, engine)
    doc = (await http.get("/api/v1/export")).json()
    report = (await http.post("/api/v1/import", json=doc)).json()
    assert report["applied"] is True
    assert {(r["kind"], r["name"], r["outcome"]) for r in report["results"]} == {
        ("upstream", "weather", "skipped"),
        ("bundle", "b1", "skipped"),
        ("endpoint", "b1-api", "skipped"),
    }
    stored = (await http.get("/api/v1/upstreams/weather")).json()
    assert stored["static_header_names"] == ["Authorization"]


async def test_mgmt19_import_reports_per_resource_and_dry_run_writes_nothing(gateway, engine):
    """MGMT-19: created and updated are reported; a dry run reports the same and writes nothing."""
    http, _ = gateway
    await _configure(http, engine)
    doc = (await http.get("/api/v1/export")).json()
    doc["bundles"][0]["description"] = "changed"
    doc["bundles"].append({"name": "b2", "upstreams": ["weather"]})
    dry = (await http.post("/api/v1/import", params={"dry_run": True}, json=doc)).json()
    outcomes = {r["name"]: r["outcome"] for r in dry["results"]}
    assert outcomes["b1"] == "updated" and outcomes["b2"] == "created"
    assert dry["dry_run"] is True and dry["applied"] is False
    assert (await http.get("/api/v1/bundles/b2")).status_code == 404
    assert (await http.get("/api/v1/bundles/b1")).json()["description"] == "first"

    real = (await http.post("/api/v1/import", json=doc)).json()
    assert {r["name"]: r["outcome"] for r in real["results"]} == outcomes
    assert (await http.get("/api/v1/bundles/b2")).status_code == 200


async def test_mgmt19_one_error_rolls_the_document_back(gateway):
    """MGMT-19: an endpoint naming an unknown bundle errors, and nothing else lands."""
    http, _ = gateway
    doc = {
        "upstreams": [{"name": "fresh", "url": "http://fresh/mcp"}],
        "endpoints": [
            {"name": "ok", "bundle_name": "nowhere", "auth_modes": ["api_key"]},
        ],
    }
    report = (await http.post("/api/v1/import", json=doc)).json()
    assert report["applied"] is False
    errors = [r for r in report["results"] if r["outcome"] == "error"]
    assert [r["name"] for r in errors] == ["ok"]
    assert (await http.get("/api/v1/upstreams/fresh")).status_code == 404


async def test_mgmt19_an_unsupported_version_is_refused(gateway):
    """MGMT-19: version 2 is rejected with 422 and nothing is written."""
    http, _ = gateway
    resp = await http.post(
        "/api/v1/import", json={"version": 2, "upstreams": [{"name": "x", "url": "http://x/mcp"}]}
    )
    assert resp.status_code == 422
    assert (await http.get("/api/v1/upstreams/x")).status_code == 404


async def test_mgmt18_a_placeholder_with_nothing_stored_is_an_error(gateway):
    """MGMT-18: the upstream errors, naming the missing secret."""
    http, _ = gateway
    doc = {
        "upstreams": [
            {
                "name": "new",
                "url": "http://new/mcp",
                "static_headers": {"X-Key": {"$secret": "X-Key"}},
            }
        ]
    }
    report = (await http.post("/api/v1/import", json=doc)).json()
    (result,) = report["results"]
    assert result["outcome"] == "error" and "X-Key" in result["message"]


async def test_mgmt20_import_deletes_nothing(gateway, engine):
    """MGMT-20, BND-32: resources and bundle content the document omits survive."""
    http, _ = gateway
    await _configure(http, engine)
    await http.put("/api/v1/upstreams/legacy", json={"name": "legacy", "url": "http://l/mcp"})
    doc = (await http.get("/api/v1/export")).json()
    doc["upstreams"] = [u for u in doc["upstreams"] if u["name"] != "legacy"]
    doc["bundles"][0]["resources"] = []
    await http.post("/api/v1/import", json=doc)
    assert (await http.get("/api/v1/upstreams/legacy")).status_code == 200
    assert (await http.get("/api/v1/bundles/b1/resources/handbook")).status_code == 200


async def test_mgmt19_curation_of_an_undiscovered_tool_is_skipped(gateway):
    """MGMT-19: a tool the target has not discovered is reported skipped, not failed."""
    http, _ = gateway
    doc = {
        "upstreams": [{"name": "fresh", "url": "http://fresh/mcp"}],
        "bundles": [
            {
                "name": "b9",
                "upstreams": [{"name": "fresh", "tools": [{"tool": "later", "enabled": False}]}],
            }
        ],
    }
    report = (await http.post("/api/v1/import", json=doc)).json()
    assert report["applied"] is True
    curation = next(r for r in report["results"] if r["kind"] == "curation")
    assert curation["name"] == "b9/fresh/later" and curation["outcome"] == "skipped"
    assert "re-import after discovery" in curation["message"]


async def test_sec11_a_service_key_cannot_export_secrets(gateway, engine):
    """SEC-11: include_secrets with a service key answers 403 and returns no value."""
    http, _ = gateway
    await _configure(http, engine)
    resp = await http.get("/api/v1/export", params={"include_secrets": True})
    assert resp.status_code == 403
    assert SECRET not in resp.text


async def test_sec11_ops18_an_admin_export_with_secrets_is_flagged_and_audited(
    gateway, engine, redis
):
    """SEC-11, OPS-18, MGMT-21: values and a warning; a management audit record; no identity."""
    http, app = gateway
    await _configure(http, engine)
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
    resp = await http.get("/api/v1/export", params={"include_secrets": True})
    assert resp.status_code == 200, resp.text
    doc = resp.json()
    assert doc["upstreams"][0]["static_headers"] == {"Authorization": SECRET}
    assert doc["upstreams"][0]["upstream_oauth"]["client_secret"] == CLIENT_SECRET
    assert "credentials" in doc["warning"]
    assert not {"users", "api_keys", "audit_records", "oauth_clients"} & set(doc)
    BootstrapDocument.model_validate(doc)
    async with session_factory(engine)() as db:
        records = (await db.execute(select(AuditRecordRow))).scalars().all()
    (record,) = [r for r in records if r.kind == "management"]
    assert record.action == "export.secrets_included" and record.user_id == admin.id
    assert SECRET not in record.model_dump_json()


async def test_sec11_default_export_needs_no_special_rights(gateway):
    """SEC-11: a service key exports with placeholders and without a warning."""
    http, _ = gateway
    resp = await http.get("/api/v1/export")
    assert resp.status_code == 200 and "warning" not in resp.json()


async def test_mgmt21_an_import_never_creates_api_keys(gateway):
    """MGMT-21: a document carrying api_keys is refused by the import, and nothing lands."""
    http, _ = gateway
    doc = {
        "upstreams": [{"name": "fresh", "url": "http://fresh/mcp"}],
        "api_keys": [{"name": "ci", "value_from_env": "CI_KEY"}],
    }
    report = (await http.post("/api/v1/import", json=doc)).json()
    assert report["applied"] is False
    assert [(r["kind"], r["outcome"]) for r in report["results"]] == [("api_key", "error")]
    assert (await http.get("/api/v1/upstreams/fresh")).status_code == 404
