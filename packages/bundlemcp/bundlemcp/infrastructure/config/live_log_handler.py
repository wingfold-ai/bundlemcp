"""Copying log events into the live log view's send queue, never blocking the logger."""

import json
import logging
import queue
from typing import Any

from bundlemcp.application.contracts.live_state.live_log_entry import LiveLogEntry
from bundlemcp.infrastructure.config.structured_logging import json_event_formatter

# the publisher's own messages must not feed the queue it drains
PUBLISHER_LOGGER = "bundlemcp.infrastructure.valkey.live_log_publisher"
MAX_VALUE_CHARS = 2048
MAX_FIELDS_CHARS = 8192
QUEUE_CAPACITY = 10_000
# lifted out of the fields, so the view can filter on them
STANDARD_KEYS = ("timestamp", "level", "logger", "event")


class LiveLogHandler(logging.Handler):
    """A logging handler that queues each event for the live log, as the process log renders it.

    It renders a record with the process log's own JSON formatter, so an entry
    holds exactly the already-redacted fields of the process log line. A full
    queue drops the event and counts it: logging never waits on the live view.
    """

    def __init__(self, level: str, *, replica: str, capacity: int = QUEUE_CAPACITY) -> None:
        super().__init__(logging.getLevelNamesMapping()[level.upper()])
        self.setFormatter(json_event_formatter())
        self.queue: queue.Queue[LiveLogEntry] = queue.Queue(maxsize=capacity)
        self.dropped = 0
        self._replica = replica

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith(PUBLISHER_LOGGER):
            return
        try:
            event: dict[str, Any] = json.loads(self.format(record))
            entry = self._entry(event)
        except Exception:  # a record that cannot be rendered is the process log's to report
            return
        try:
            self.queue.put_nowait(entry)
        except queue.Full:
            self.dropped += 1

    def drain(self, limit: int) -> list[LiveLogEntry]:
        """Up to ``limit`` queued entries, oldest first."""
        drained: list[LiveLogEntry] = []
        while len(drained) < limit:
            try:
                drained.append(self.queue.get_nowait())
            except queue.Empty:
                break
        return drained

    def _entry(self, event: dict[str, Any]) -> LiveLogEntry:
        fields = {
            key: _truncated(value) for key, value in event.items() if key not in STANDARD_KEYS
        }
        if len(json.dumps(fields, default=str)) > MAX_FIELDS_CHARS:
            fields = {"truncated": True}
        return LiveLogEntry(
            timestamp=str(event.get("timestamp", "")),
            level=str(event.get("level", "info")),
            logger=event.get("logger"),
            event=str(event.get("event", "")),
            replica=self._replica,
            endpoint=_text(event.get("endpoint")),
            upstream=_text(event.get("server")),
            fields=fields,
        )


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _truncated(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_VALUE_CHARS:
        return value[:MAX_VALUE_CHARS] + "…"
    return value
