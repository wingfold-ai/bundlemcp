"""The audit writer retries, drains on shutdown, and names every record it loses (OPS-3, OPS-7)."""

import asyncio

import pytest
from bundlemcp.application.contracts.observability.gateway_metrics import AuditDropReason
from bundlemcp.domain.audit.audit_record import AuditRecord
from bundlemcp.domain.audit.audit_status import AuditStatus
from bundlemcp.infrastructure.memory.recording_metrics import RecordingMetrics
from bundlemcp.infrastructure.postgres.audit_writer import QUEUE_MAX, QueuedAuditWriter
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.audit_record_row import AuditRecordRow
from sqlalchemy import event, func, select
from sqlalchemy.exc import OperationalError
from structlog.testing import capture_logs


def _record(key: str) -> AuditRecord:
    return AuditRecord(
        endpoint_name="main",
        bundle_name="demo",
        presented_tool_name="echo__say",
        status=AuditStatus.SUCCESS,
        idempotency_key=key,
    )


class Outage:
    """Inserts fail the way a lost connection does, a set number of times or until healed."""

    def __init__(self, engine, failures: int | None) -> None:
        self.engine = engine
        self.failures = failures

    def __call__(self, conn, cursor, statement, *args):
        if not statement.lstrip().upper().startswith("INSERT"):
            return
        if self.failures is None or self.failures > 0:
            if self.failures is not None:
                self.failures -= 1
            raise OperationalError(statement, {}, ConnectionRefusedError("refused"))

    def __enter__(self):
        event.listen(self.engine.sync_engine, "before_cursor_execute", self)
        return self

    def __exit__(self, *exc):
        event.remove(self.engine.sync_engine, "before_cursor_execute", self)


async def _count(engine) -> int:
    async with session_factory(engine)() as db:
        return (await db.execute(select(func.count()).select_from(AuditRecordRow))).scalar_one()


async def _no_wait(_seconds: float) -> None:
    await asyncio.sleep(0)


async def test_ops3_transient_failure_is_retried(engine):
    """OPS-3: a record queued during a short outage is written once the database is back."""
    writer = QueuedAuditWriter(session_factory(engine), RecordingMetrics(), sleep=_no_wait)
    await writer.start()
    with Outage(engine, failures=3), capture_logs() as logs:
        writer.record(_record("k-1"))
        await writer.drain()
    await writer.stop()
    assert await _count(engine) == 1
    assert not any(entry["event"] == "audit.write_failed" for entry in logs)


async def test_ops3_persistent_failure_logged_with_key(engine):
    """OPS-3: once the retry period is over, the record is logged with its key and counted."""
    metrics = RecordingMetrics()
    writer = QueuedAuditWriter(
        session_factory(engine), metrics, retry_seconds=0.01, sleep=_no_wait
    )
    await writer.start()
    with Outage(engine, failures=None), capture_logs() as logs:
        writer.record(_record("k-lost"))
        await writer.drain()
    await writer.stop()
    [failed] = [entry for entry in logs if entry["event"] == "audit.write_failed"]
    assert failed["idempotency_key"] == "k-lost"
    assert metrics.events[-1] == ("audit_dropped", {"reason": AuditDropReason.WRITE_FAILED})


async def test_ops3_overflow_logged_with_key_and_counted(engine):
    """OPS-3, OPS-7: a record submitted to a full queue is dropped, logged with its key and
    counted; the call that submitted it is unaffected."""
    metrics = RecordingMetrics()
    writer = QueuedAuditWriter(session_factory(engine), metrics)  # not started: nothing drains
    for n in range(QUEUE_MAX):
        writer.record(_record(f"k-{n}"))
    with capture_logs() as logs:
        writer.record(_record("k-overflow"))
    [overflow] = [entry for entry in logs if entry["event"] == "audit.queue_overflow"]
    assert overflow["idempotency_key"] == "k-overflow"
    assert metrics.count("audit_dropped") == 1
    assert writer.queue_depth == QUEUE_MAX


async def test_ops3_writes_go_in_batches(engine):
    writer = QueuedAuditWriter(session_factory(engine), RecordingMetrics())
    for n in range(250):
        writer.record(_record(f"k-{n}"))
    await writer.start()
    await writer.drain()
    await writer.stop()
    assert await _count(engine) == 250


async def test_ops3_shutdown_drains_queue(engine):
    """OPS-3: with the database reachable, all 50 queued records are committed on shutdown."""
    writer = QueuedAuditWriter(session_factory(engine), RecordingMetrics())
    await writer.start()
    for n in range(50):
        writer.record(_record(f"k-{n}"))
    await writer.stop()
    assert await _count(engine) == 50


@pytest.mark.parametrize("queued", [1, 5])
async def test_ops3_drain_deadline_names_lost_records(engine, queued):
    """OPS-3: with the database unreachable, each record still unwritten when the drain runs out
    is logged as lost on shutdown with its key."""
    metrics = RecordingMetrics()
    writer = QueuedAuditWriter(session_factory(engine), metrics, sleep=_no_wait)
    await writer.start()
    with Outage(engine, failures=None), capture_logs() as logs:
        for n in range(queued):
            writer.record(_record(f"k-{n}"))
        await asyncio.sleep(0.01)
        await writer.stop(deadline=0.05)
    lost = sorted(e["idempotency_key"] for e in logs if e["event"] == "audit.lost_on_shutdown")
    assert lost == sorted(f"k-{n}" for n in range(queued))
    assert metrics.count("audit_dropped") == queued
