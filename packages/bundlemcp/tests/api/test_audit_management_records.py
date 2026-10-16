"""Management actions share the audit log with tool calls, told apart by kind (OPS-18)."""

import csv
import io
from datetime import UTC, datetime

from bundlemcp.domain.audit.audit_record import AuditRecord
from bundlemcp.domain.audit.audit_status import AuditStatus
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWorkFactory

from tests.api.test_gateway import _initialize, _rpc, _running
from tests.conftest import SERVICE_KEY, seed_api_key

EXPORTED = "export.secrets_included"


async def _seed(engine, redis) -> None:
    units = SqlAlchemyUnitOfWorkFactory(session_factory(engine), redis)
    async with units.open() as uow:
        uow.audit_records.add(
            AuditRecord(
                created_at=datetime(2026, 10, 1, tzinfo=UTC),
                endpoint_name="main",
                bundle_name="demo",
                presented_tool_name="echo__say",
                status=AuditStatus.SUCCESS,
            )
        )
        uow.audit_records.add(
            AuditRecord.management_event(EXPORTED, user_id=None, api_key_id=None, auth_method=None)
        )
        await uow.commit()


async def test_ops18_list_filters_by_kind(service_client, engine, redis):
    """OPS-18: kind=management lists only the management record, kind=tool_call the rest."""
    await _seed(engine, redis)
    management = (
        await service_client.get("/api/v1/audit-records", params={"kind": "management"})
    ).json()
    tool_calls = (
        await service_client.get("/api/v1/audit-records", params={"kind": "tool_call"})
    ).json()
    everything = (await service_client.get("/api/v1/audit-records")).json()

    assert management["total"] == 1
    [record] = management["items"]
    assert record["kind"] == "management" and record["action"] == EXPORTED
    assert record["status"] == "success"
    assert record["endpoint_name"] == "" and record["bundle_name"] == ""
    assert record["tool_name"] is None and record["presented_tool_name"] is None
    assert [r["kind"] for r in tool_calls["items"]] == ["tool_call"]
    assert everything["total"] == 2


async def test_ops18_list_rejects_unknown_kind(service_client):
    """OPS-18: a kind other than tool_call or management is a validation error."""
    resp = await service_client.get("/api/v1/audit-records", params={"kind": "other"})
    assert resp.status_code == 422


async def test_ops18_export_carries_kind_and_action(service_client, engine, redis):
    """OPS-18: the CSV export has kind and action columns, and honours the kind filter."""
    await _seed(engine, redis)
    resp = await service_client.get("/api/v1/audit-records:export")
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    assert {"kind", "action"} <= set(rows[0])
    assert {(row["kind"], row["action"]) for row in rows} == {
        ("management", EXPORTED),
        ("tool_call", ""),
    }

    filtered = await service_client.get(
        "/api/v1/audit-records:export", params={"kind": "management"}
    )
    [row] = list(csv.DictReader(io.StringIO(filtered.text)))
    assert row["action"] == EXPORTED


async def test_ops18_tool_call_record_has_kind_tool_call_and_no_action(engine, redis):
    """OPS-18: a tool call through an endpoint is recorded as kind tool_call with no action."""
    await seed_api_key(engine, SERVICE_KEY)
    async with _running(engine, redis) as (http, app):
        session = await _initialize(http)
        await _rpc(
            http, "main", session, "tools/call", {"name": "echo__say", "arguments": {"text": "x"}}
        )
        await app.state.container.audit.drain()
        resp = await http.get(
            "/api/v1/audit-records", headers={"Authorization": f"Bearer {SERVICE_KEY}"}
        )
    [record] = resp.json()["items"]
    assert record["kind"] == "tool_call"
    assert record["action"] is None
    assert record["presented_tool_name"] == "echo__say"
