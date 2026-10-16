# Design

## Context

See proposal.md for motivation. Today `configure_logging` (`infrastructure/config/structured_logging.py`) routes
structlog and stdlib records (uvicorn included) through one `ProcessorFormatter` to a single `StreamHandler` on
**stderr** (its docstring says stdout; `fix-stale-documentation` corrects that). Nothing binds request context
(endpoint, upstream, session) to the log context yet. The Valkey client and the background tasks that use it (signal
bus, invalidation subscriber) are built in the composition root. The rule from CLAUDE.md applies: no in-memory-only
state a request depends on — a per-process buffer is acceptable only as a short send queue, never as the source the UI
reads.

## Goals / Non-Goals

**Goals:**

- One view of every replica's events, near real time (a few seconds), with filters.
- Logging stays fast and safe: no request waits on Valkey, a Valkey outage costs nothing but the live view.
- The buffer can never hold more than the process log does (OPS-17).

**Non-Goals:**

- Durable history, search, retention, alerting.
- A redaction layer of its own: redaction is OPS-8's job at the point of logging.

## Decisions

### D1. A logging handler feeding a bounded queue, drained by a background publisher

A second stdlib `logging.Handler` (`LiveLogHandler`, `infrastructure/config/`) is attached to the root logger beside the
stderr handler, with its own level from `BUNDLEMCP_LIVE_LOG_LEVEL` (default `INFO`, same pattern as `log_level`). It
renders the record to the same event dict the JSON renderer sees (via the shared processor chain) and puts it on a
bounded `asyncio.Queue` (`put_nowait`; when full, the event is dropped and a drop counter incremented). A background
task (`ValkeyLiveLogPublisher`, `infrastructure/valkey/`) drains the queue in batches and appends with one pipelined
`XADD bmcp:logs MAXLEN ~ 10000` per batch, tagging each entry with the replica id.

*Alternatives:* a structlog processor (misses stdlib loggers such as uvicorn's access log); an `XADD` per event in the
request path (puts a Valkey round trip into every log call); pub/sub instead of a stream (no backfill, no resume, an
admin who connects late sees nothing).

The publisher's own failures are logged through a logger excluded from the live handler, and at most once per outage,
so a Valkey outage cannot feed back into the queue.

### D2. Contract and layers

- `application/contracts/live_state/live_log_buffer.py` — `LiveLogBuffer` protocol: `append(entries)`,
  `read_after(cursor, limit)`, `follow(cursor)`; entries are a `LiveLogEntry` model (id, time, level, logger, event,
  replica, endpoint, upstream, fields).
- `infrastructure/valkey/live_log_buffer.py` — the stream adapter (`XADD`, `XREVRANGE` for backfill, `XREAD BLOCK` for
  follow); `infrastructure/memory/` — a fake for tests.
- `application/` — `LiveLogService` applying the filters (level, text, upstream, endpoint) to entries; filtering is
  server-side so a busy gateway does not ship every line to the browser.
- `api/management/controllers/live_log_controller.py` — a `ManagementController`: `GET /logs` (backfill, newest N) and
  `GET /logs/stream` (Server-Sent Events, `id:` = stream entry id, honours `Last-Event-ID` and a `since` query).

### D3. Server-Sent Events, not WebSocket

The management API is plain HTTP behind `ManagementAuth`; SSE uses the admin cookie unchanged (EventSource sends
cookies on same-site requests), passes the CSRF rules untouched because it is a `GET`, and resumes natively through
`Last-Event-ID`. A WebSocket would need its own auth handshake and gives nothing back, since the stream is one-way.
Pause in the UI closes the stream and remembers the last id; resume reopens from it (OPS-15).

### D4. What an entry carries

The event dict after the shared processors, minus the renderer: `timestamp`, `level`, `logger`, `event`, and the bound
key/values. Values are truncated to 2 KiB each and an entry to 8 KiB, so one oversized event cannot dominate the
buffer. `endpoint` and `upstream` are lifted to top-level fields when the log context carries them (see the dependency
on `improve-request-observability`).

## Risks / Trade-offs

- [High request rates at `INFO` turn every access log line into a Valkey write] → batching keeps it to one pipeline per
  drain cycle; operators can raise `BUNDLEMCP_LIVE_LOG_LEVEL`; dropped events are counted, not retried.
- [An event logged with a secret reaches the buffer] → the same bug would already leak to the process log (OPS-8); a
  test asserts the buffer equals the rendered process line for representative requests (OPS-17).
- [Many open UI tabs each hold an `XREAD BLOCK` connection] → each stream uses a dedicated connection with a short
  block timeout; the number of concurrent streams per replica is capped and excess requests get `429`.
- [Filtering by endpoint/upstream is incomplete before `improve-request-observability`] → documented; the filter
  matches entries that carry the field.

## Migration Plan

Additive. The Valkey key `bmcp:logs` is new; deleting it is harmless. Rollback removes the handler and the routes.

## Open Questions

- Whether the live-log threshold should later become a runtime config key; the config registry holds only numeric and
  boolean values today, so it starts as an environment setting.
