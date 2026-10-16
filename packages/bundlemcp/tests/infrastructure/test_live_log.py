"""The live log buffer and how events reach it (OPS-14, OPS-16, OPS-17, ARC-8)."""

import json
import logging

import structlog
from bundlemcp.application.contracts.live_state.live_log_entry import LiveLogEntry
from bundlemcp.application.management.live_log_filter import LiveLogFilter
from bundlemcp.application.management.live_log_service import LiveLogService
from bundlemcp.infrastructure.config.live_log_handler import LiveLogHandler
from bundlemcp.infrastructure.config.structured_logging import (
    configure_logging,
    json_event_formatter,
)
from bundlemcp.infrastructure.memory.in_memory_live_log_buffer import InMemoryLiveLogBuffer
from bundlemcp.infrastructure.valkey.live_log_buffer import LIVE_LOG_KEY, ValkeyLiveLogBuffer
from bundlemcp.infrastructure.valkey.live_log_publisher import LiveLogPublisher


def _entry(event: str, **fields) -> LiveLogEntry:
    return LiveLogEntry(timestamp="t", level="info", event=event, replica="r1", **fields)


async def test_ops14_the_stream_stays_capped(redis):
    """OPS-14: after more than ten thousand events, about the newest ten thousand remain."""
    buffer = ValkeyLiveLogBuffer(redis)
    for start in range(0, 10_500, 500):
        await buffer.append([_entry(f"e{n}") for n in range(start, start + 500)])
    length = await redis.xlen(LIVE_LOG_KEY)
    assert 10_000 <= length <= 10_500
    newest = await buffer.latest(1)
    assert newest[0].event == "e10499"


async def test_ops16_entries_after_a_cursor_come_in_order(redis):
    """OPS-16, OPS-15: following from an id returns what came after it, oldest first."""
    buffer = ValkeyLiveLogBuffer(redis)
    await buffer.append([_entry("one"), _entry("two")])
    (first, second) = await buffer.latest(2)
    await buffer.append([_entry("three")])
    after = await buffer.after(first.id, limit=10, wait_seconds=0.1)
    assert [e.event for e in after] == ["two", "three"]
    assert await buffer.after(after[-1].id, limit=10, wait_seconds=0.05) == []
    del second


def _logger_with(handler: logging.Handler, name: str = "bundlemcp.test") -> structlog.BoundLogger:
    configure_logging("DEBUG")
    logging.getLogger().addHandler(handler)
    return structlog.get_logger(name)


async def test_ops14_events_below_the_threshold_are_not_published():
    """OPS-14: with the threshold at WARNING an INFO event stays in the process log only."""
    handler = LiveLogHandler("WARNING", replica="r1")
    log = _logger_with(handler)
    try:
        log.info("quiet")
        log.warning("loud")
    finally:
        logging.getLogger().removeHandler(handler)
    assert [entry.event for entry in handler.drain(10)] == ["loud"]


async def test_ops14_a_full_queue_drops_instead_of_blocking():
    """OPS-14: logging never waits on the live view; overflow is counted."""
    handler = LiveLogHandler("INFO", replica="r1", capacity=2)
    log = _logger_with(handler)
    try:
        for n in range(5):
            log.info("burst", n=n)
    finally:
        logging.getLogger().removeHandler(handler)
    assert len(handler.drain(10)) == 2 and handler.dropped == 3


async def test_ops14_events_from_two_replicas_share_one_buffer():
    """OPS-14: each replica's events land in the one buffer, tagged with that replica."""
    buffer = InMemoryLiveLogBuffer()
    for replica in ("a", "b"):
        handler = LiveLogHandler("INFO", replica=replica)
        log = _logger_with(handler)
        try:
            log.info("hello")
        finally:
            logging.getLogger().removeHandler(handler)
        await LiveLogPublisher(handler, buffer).flush()
    assert sorted(entry.replica for entry in buffer.entries) == ["a", "b"]


async def test_ops14_a_store_outage_costs_only_the_live_view():
    """OPS-14: a failing buffer neither raises into the logger nor stops later batches."""

    class Down:
        calls = 0

        async def append(self, entries):
            Down.calls += 1
            raise ConnectionError("store down")

    handler = LiveLogHandler("INFO", replica="r1")
    log = _logger_with(handler)
    try:
        log.info("during outage")
        await LiveLogPublisher(handler, Down()).flush()
        log.info("still logging")
        await LiveLogPublisher(handler, Down()).flush()
    finally:
        logging.getLogger().removeHandler(handler)
    assert Down.calls == 2


async def test_ops17_an_entry_holds_exactly_the_process_log_line():
    """OPS-17: the entry is the rendered process log line, so it can carry nothing more."""
    handler = LiveLogHandler("INFO", replica="r1")
    log = _logger_with(handler)
    captured: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record):
            captured.append(self.format(record))

    process = Capture()
    process.setFormatter(json_event_formatter())
    logging.getLogger().addHandler(process)
    try:
        structlog.contextvars.bind_contextvars(endpoint="b1-api", server="weather")
        log.info("http.request", status=200, api_key_id="k-1")
    finally:
        structlog.contextvars.clear_contextvars()
        logging.getLogger().removeHandler(handler)
        logging.getLogger().removeHandler(process)
    (entry,) = handler.drain(10)
    line = json.loads(captured[-1])
    assert (entry.endpoint, entry.upstream) == ("b1-api", "weather")
    assert entry.fields == {
        k: v for k, v in line.items() if k not in ("timestamp", "level", "logger", "event")
    }
    assert entry.event == line["event"] and entry.level == line["level"]


async def test_ops15_the_service_filters_and_resumes_without_duplicates():
    """OPS-15: level, text, endpoint and upstream filters, and resume from the last id seen."""
    buffer = InMemoryLiveLogBuffer()
    await buffer.append(
        [
            LiveLogEntry(
                timestamp="t", level="error", event="boom", replica="r", endpoint="b1-api"
            ),
            LiveLogEntry(timestamp="t", level="info", event="fine", replica="r", endpoint="b1-api"),
            LiveLogEntry(timestamp="t", level="error", event="other", replica="r", upstream="w"),
        ]
    )
    service = LiveLogService(buffer)
    errors = await service.recent(LiveLogFilter(level="error", endpoint="b1-api"), limit=10)
    assert [e.event for e in errors] == ["boom"]
    assert [e.event for e in await service.recent(LiveLogFilter(text="OTH"), limit=10)] == ["other"]
    assert [e.event for e in await service.recent(LiveLogFilter(upstream="w"), limit=10)] == [
        "other"
    ]
    paused_at = buffer.entries[0].id
    follow = service.follow(LiveLogFilter(), after=paused_at, wait_seconds=0.1)
    batch = await anext(follow)
    assert [e.event for e in batch] == ["fine", "other"]
