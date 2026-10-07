# 52 — Live logs view

**Status:** Accepted · **Origin:** metamcp carry-over (moved from process memory to Redis) **Prior art:**
`../metamcp/apps/backend/src/lib/metamcp/log-store.ts` (in-memory), frontend `live-logs/` page

## Summary

A near-real-time log view in the admin UI for debugging endpoints and upstreams without shelling into containers. Backed
by Redis so it works with multiple replicas (metamcp's version was per-process memory).

## Requirements

- **LOG-1** Gateway log events (the structured events from [OBS-1](51-observability.md), level ≥ configurable threshold,
  plus connection/session lifecycle events) are published to a Redis Stream capped ring buffer (`MAXLEN ~10k`),
  aggregating across replicas.
- **LOG-2** UI page streams new entries (SSE or websocket from the management API, admin-authenticated) with
  pause/resume, level filter, and free-text + server/endpoint filter.
- **LOG-3** The buffer is best-effort ephemeral: Redis loss clears it — acceptable by design; durable history is the
  audit log and stdout logs.
- **LOG-4** Same redaction rules as OBS-1 (the stream carries already-redacted events, never raw
  headers/tokens/arguments).

## Out of scope

- Log persistence, search over history, retention (use the container platform's log stack).

## Open questions

- None.
