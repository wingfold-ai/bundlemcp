# Proposal

## Why

Debugging an endpoint or an upstream today means shelling into the container and reading its log output, one replica
at a time. The admin UI's *Live logs* page is a placeholder (`apps/web/app/pages/logs.vue`,
`data-testid="logs-placeholder"`). metamcp had a live log view, but kept it in one Node process's memory
(`../metamcp/apps/backend/src/lib/metamcp/log-store.ts`), which breaks with a second replica — exactly the flaw
bundlemcp exists to avoid. A capped stream in Valkey gives every replica's events in one view.

## What Changes

- Every log event at or above a configurable threshold (`BUNDLEMCP_LIVE_LOG_LEVEL`) is also appended to a capped
  Valkey stream (about 10,000 entries) shared by all replicas, without blocking the request that logged it.
- The management API serves the buffer as a server-push stream (admin session or service key) with level, free-text,
  upstream and endpoint filters, resumable from the last entry seen.
- The admin UI's *Live logs* page replaces the placeholder: live tail, pause/resume, filters.
- The buffer is ephemeral by design; it carries the same redacted events as the process log.
- `architecture`'s ARC-8 lists the live-log ring buffer among the RESP store's contents again.

Out of scope (carried from the original spec): log persistence, search over history, and retention — use the container
platform's log stack.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `operations`: adds OPS-14..OPS-17 — the cross-replica buffer, the streaming API and UI page, ephemerality, and
  redaction. On archive, extend the slice's Purpose to mention the live log view.
- `architecture`: ARC-8 — the RESP store also holds the live-log ring buffer.

## Impact

- Code: a log-publishing hook in the structured logging setup (`infrastructure/config/`), a buffer contract in
  `application/contracts/live_state/` with a Valkey adapter and a memory fake, a controller under
  `api/management/controllers/`, a setting in `Settings`, and the Nuxt page.
- API: a new streaming route and a backfill route; `cd apps/web && npm run openapi`.
- UI tests: `apps/web/tests/login.spec.ts` asserts the `logs-placeholder` marker and must assert the real page instead.
- Docs: `docs/self-hosting/operations.md` (says there is no live log stream), `docs/self-hosting/configuration.md`
  (the new setting), and arc42 §5/§8 for the buffer.
- Dependency: the upstream and endpoint filters of OPS-15 need each request's log events to carry the endpoint and
  upstream they concern, which the process log does not bind today. Change `improve-request-observability` (OPS-8)
  adds that context; until it lands those two filters can only match events that name them explicitly.
- ADR: one new ADR (next free number) for log fan-out through a capped Valkey stream rather than per-process memory or
  a log-shipping sidecar.
