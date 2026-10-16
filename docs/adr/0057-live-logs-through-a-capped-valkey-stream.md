# ADR-0057: Live logs fan out through a capped Valkey stream

**Status:** accepted · **Date:** 2026-10-16

## Context

Debugging an endpoint or an upstream meant reading container logs, one replica at a time; the admin UI's Live logs page
was a placeholder. metamcp kept its live log in one process's memory, which a second replica breaks — the very flaw
bundlemcp exists to avoid.

## Decision drivers

- One view of every replica's events, within seconds, with filters.
- Logging stays fast: no request waits on the store, and a store outage costs only the live view.
- The view can never hold more than the process log does.

## Decision

- **A second logging handler** sits beside the standard-error handler, with its own threshold
  (`BUNDLEMCP_LIVE_LOG_LEVEL`). It renders each record with the process log's own JSON formatter, so an entry is the
  process log line and nothing more, and puts it on a bounded queue; a full queue drops and counts.
- **A background publisher** drains the queue in batches into one Valkey stream, `bmcp:logs`, trimmed to about
  10,000 entries, each tagged with the replica. Its failures are logged once per outage, by a logger the handler skips.
- **The management API serves it**: `GET /api/v1/logs` for the recent entries and `GET /api/v1/logs/stream` as
  Server-Sent Events with the entry id as event id, so a paused or dropped view resumes from `Last-Event-ID` without
  gaps or duplicates. Filters run on the gateway. Each replica caps its open streams and answers `429` beyond.
- **Ephemeral by design.** History, search and retention belong to the container platform's log stack.

## Alternatives considered

- **Per-process memory.** One replica's events only, and lost on restart.
- **Pub/sub instead of a stream.** No backfill and no resume; a view opened late sees nothing.
- **A write per event in the request path.** Puts a store round trip into every log call.
- **A structlog processor instead of a handler.** Misses the standard-library loggers.
- **WebSocket.** Needs its own authentication handshake for a one-way stream; SSE uses the admin cookie unchanged.

## Consequences

### Positive

- One live view across replicas, filterable and resumable.

### Trade-offs

- At `INFO`, every access line becomes a buffer write, batched; operators can raise the threshold.
- Each open view holds a blocking read on the store for up to ten seconds at a time.
