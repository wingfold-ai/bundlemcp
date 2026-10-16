"""The audit export answers the whole filtered result as CSV (OPS-6)."""

import csv
import io
from datetime import UTC, datetime, timedelta

from bundlemcp.domain.audit.audit_record import AuditRecord
from bundlemcp.domain.audit.audit_status import AuditStatus
from bundlemcp.domain.shared.secrets import API_KEY_PREFIX, generate_token
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWorkFactory

from tests.conftest import seed_api_key, serving

NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)


async def _seed(engine, redis, count: int, status: AuditStatus, *, key_id=None) -> None:
    units = SqlAlchemyUnitOfWorkFactory(session_factory(engine), redis)
    async with units.open() as uow:
        for n in range(count):
            uow.audit_records.add(
                AuditRecord(
                    created_at=NOW - timedelta(seconds=n),
                    endpoint_name="main",
                    bundle_name="demo",
                    status=status,
                    api_key_id=key_id,
                    idempotency_key=f"k-{status.value}-{n}",
                )
            )
        await uow.commit()


def _rows(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


async def test_ops6_export_applies_list_filters(service_client, engine, redis):
    """OPS-6: the export contains exactly what the list returns for the same filters."""
    await _seed(engine, redis, 3, AuditStatus.ERROR)
    await _seed(engine, redis, 2, AuditStatus.SUCCESS)
    exported = await service_client.get("/api/v1/audit-records:export", params={"status": "error"})
    listed = await service_client.get("/api/v1/audit-records", params={"status": "error"})
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    rows = _rows(exported.text)
    assert [row["id"] for row in rows] == [item["id"] for item in listed.json()["items"]]
    assert {row["status"] for row in rows} == {"error"}


async def test_ops6_export_streams_whole_result(service_client, engine, redis):
    """OPS-6: 1200 matching records export as 1200 rows with the caller and key columns,
    though a list page holds at most 500."""
    key = await seed_api_key(engine, generate_token(API_KEY_PREFIX), name="caller")
    key_id = key.id
    await _seed(engine, redis, 1200, AuditStatus.SUCCESS, key_id=key_id)
    resp = await service_client.get("/api/v1/audit-records:export")
    rows = _rows(resp.text)
    assert len(rows) == 1200
    assert {"user_id", "api_key_id", "auth_method", "idempotency_key"} <= set(rows[0])
    assert rows[0]["api_key_id"] == str(key_id)
    assert len({row["id"] for row in rows}) == 1200  # no record twice
    assert rows[0]["created_at"] > rows[-1]["created_at"]  # newest first


async def test_ops6_export_requires_management_credentials(engine, redis):
    async with serving(engine, redis) as (http, _app):
        resp = await http.get("/api/v1/audit-records:export")
    assert resp.status_code == 401
