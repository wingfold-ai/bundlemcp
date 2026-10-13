# Proposal: complete the session lifecycle

## Why

The session model holds up for the happy path, but its edges were specified and not built. The idle lifetime is fixed
at 24 hours: the `session_lifetime` runtime key (registered in `domain/config/config_registry.py`, `0` = no expiry) is
read by nothing, records carry no timestamps and nothing sweeps them. Shutdown is not bounded and probably never starts:
the Dockerfile's `CMD ["sh", "-c", "alembic … && python main.py"]` can leave `sh` as PID 1, so SIGTERM may never reach
the app, and uvicorn runs without `timeout_graceful_shutdown`. A server→client request for a stream no replica holds
waits out the whole call timeout (`ClientRelay._roundtrip`, ~60 s) instead of failing. With Postgres down, credential
validation surfaces as an unhandled 500. The tests behind the "restarts are non-events" promise restart an idle gateway
with `docker compose restart` — same image, no load, one replica — and the 2-second propagation budget (SES-19) is not
asserted for the cases the spec names.

## What Changes

- Session records carry `created_at` and `last_active_at`; their idle lifetime is the runtime `session_lifetime` key
  (default 24 h, `0` = no idle expiry) (SES-1, SES-10).
- A periodic sweeper expires idle sessions, releasing their upstream bindings; the store TTL stays as the backstop
  (SES-10).
- Bounded graceful shutdown: readiness drops, new requests are refused, in-flight requests drain for a configurable
  window, notification streams end cleanly, then the process exits; SIGTERM reaches the gateway in the container
  (`exec`) (SES-11).
- A message for a target with no live holder fails fast with a structured error (SES-13).
- With Postgres down, credential validation and config reads answer 503 with `Retry-After`, never 500 (SES-14).
- Integration tests on the compose stack: restart under load, two-replica round-robin, upstream-restart recovery
  (SES-12); the 2-second propagation budget for endpoint disable, key deactivation and tool disable (SES-19); a rolling
  `compose up` of a new image under load (DEP-7).
- A debugging setting that disables caching, with identical behaviour (SES-22).

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `sessions`: MODIFIED SES-1 (timestamps, configurable lifetime), SES-10 (sweeper, `session_lifetime`
  wired), SES-11 (bounded drain, signals reach the process), SES-12 (restart under load, two replicas, upstream
  restart), SES-13 (fail fast without a holder), SES-14 (Postgres-down row).
- `sessions`: MODIFIED SES-19 (integration tests assert the budget) and SES-22 (cache-off debug setting).
- `deployment`: MODIFIED DEP-7 (zero downtime verified by a rolling `compose up` under load).

## Open decision

- **Serving existing sessions while Postgres is down (SES-14).** The original matrix says existing sessions "keep
  serving from cached config/tool data where possible". Today nothing is cached except runtime config (SES-22): endpoint
  lookups, bundle composition and key validation read Postgres on every request. Building it needs a last-known-good
  view cache used only when Postgres is unreachable, invalidated by the same events (and SES-22 amended to allow it).
  The delta leaves the clause out — every request that needs Postgres answers 503 — until the maintainers decide to
  build the cache.

## Impact

- **Code:** session record fields and the session store's lifetime source (`domain/sessions/`,
  `infrastructure/valkey/session_store.py`); a session sweeper (application use case + Valkey adapter, started from
  `main/`); a stream-presence contract and adapter beside the signal bus; shutdown sequencing in `main/app.py` and
  `apps/gateway/main.py`; a `StoreUnavailable` failure from the unit of work mapped to 503 in `api/`.
- **Settings:** `BUNDLEMCP_SHUTDOWN_DRAIN_SECONDS`, `BUNDLEMCP_CONFIG_CACHE_DISABLED`.
- **Deploy:** `apps/gateway/Dockerfile` (`exec`), `stop_grace_period` in `deploy/docker-compose.yml`, a two-replica
  integration overlay with a round-robin proxy.
- **Docs:** `packages/bundlemcp/bundlemcp/api/mcp/README.md` (names deleted modules — `composition.py`, `streams.py`,
  `signals.py`, `_drive_upstream` — and claims `session_lifetime` works); `docs/self-hosting/operations.md` and
  `configuration.md`; arc42 §6/§7.
- **Dependencies:** the upstream-restart recovery test (SES-12) and the sweeper's release of upstream sessions need
  [add-upstream-session-pooling](../add-upstream-session-pooling/proposal.md)'s SES-7; until it lands the sweeper only
  removes records. [add-prometheus-metrics](../add-prometheus-metrics/proposal.md) can export the sweeper's expiry
  count; without it the count is logged.
- No ADR: the decisions follow ADR-0004 and ADR-0016; no DTO or route changes.
