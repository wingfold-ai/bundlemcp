# Design: complete the session lifecycle

## Context

See proposal.md for the motivation. Today:

- `ValkeySessionStore(redis)` is built in `main/composition_root.py` with the constructor default
  `lifetime_seconds=24 * 3600`; `touch` re-applies it with `EXPIRE`. `RuntimeConfig` (application) already serves the
  `session_lifetime` key, cached per replica and invalidated by `config` events (SES-18).
- `SessionRecord` (`domain/sessions/session_record.py`, `SESSION_RECORD_VERSION = 2`) has no timestamps. A record whose
  version differs is treated as expired (DEP-6).
- `apps/gateway/main.py` calls `uvicorn.run` without `timeout_graceful_shutdown`; the image's
  `CMD ["sh", "-c", "alembic … && python main.py"]` relies on the shell to forward SIGTERM.
- `ClientRelay._roundtrip` publishes a server→client request on the signal bus and waits for the reply up to the call
  timeout. Every replica `PSUBSCRIBE`s `bmcp:signal:*`, so the `PUBLISH` receiver count says nothing about a holder.
- `StoreConnectionError`/`StoreTimeoutError` from Valkey map to 503 (`live_state_unavailable_handler`); Postgres errors
  have no handler and surface as 500.
- `tests/integration/test_smoke.py` restarts one gateway with `docker compose restart gateway`, idle.

## Goals / Non-Goals

**Goals:** a configurable, swept idle lifetime; a shutdown that drains within a known bound in the shipped image; fast
failure for unreachable stream targets; 503 instead of 500 for a Postgres outage; integration evidence for the
restart, replica and propagation promises.

**Non-Goals:** serving sessions from a stale config cache during a Postgres outage (the proposal's Open decision);
`Last-Event-ID` replay; moving in-flight calls between replicas on shutdown.

## Decisions

### D1. Timestamps without a schema-version bump

`SessionRecord` gains `created_at` and `last_active_at` (aware datetimes, described fields) with defaults, so a
version-2 record of the previous build still parses, and the previous build ignores the extra fields (the model does not
forbid extras). The version stays 2 and a rolling deploy causes no re-initialize storm. `touch` writes `last_active_at`
and the TTL in one transaction.

*Alternative:* bump to 3 with a reader for 2 — needed only once a field changes meaning; adding optional fields does
not.

### D2. The lifetime is read from runtime config at each write

The `SessionStore` contract takes the lifetime from its caller: `create(record, lifetime)` and
`touch(session_id, lifetime)`, where `lifetime` is a domain value object `SessionLifetime` (`domain/sessions/`; `0` →
no expiry, written with `PERSIST`). The MCP edge reads it from `RuntimeConfig`, so the adapter stays free of config
lookups and a changed value applies at each session's next activity (SES-10).

### D3. Sweeper over an activity index, TTL as backstop

`touch` and `create` also `ZADD bmcp:sessions:active {last_active_epoch} {session_id}`. A `SessionSweeper` use case
(`application/sessions/session_sweeper.py`) runs every 60 s on one replica at a time under a Valkey lease (the UPS-23
lease pattern) and, for ids scored older than the lifetime: loads the record, releases its upstream bindings through
the upstream-session pool contract when [add-upstream-session-pooling](../add-upstream-session-pooling/proposal.md) has
landed, deletes record and index entry, and counts the expiry (a log line `session.expired`, or the OPS-9 metric when
present). The record's TTL is set to the lifetime plus two sweep intervals, so the sweeper normally expires sessions
with their bindings in hand, and the TTL removes them if no sweeper runs. Ids whose record is already gone are just
removed from the index.

*Alternative:* Valkey keyspace notifications on expiry — fire-and-forget, lost while no subscriber is connected, and the
record (with its bindings) is already gone when they arrive.

### D4. Shutdown sequence

- **Signal delivery.** `CMD ["sh", "-c", "alembic -c alembic.ini upgrade head && exec python main.py"]`: `exec` replaces
  the shell, so the Python process receives SIGTERM directly. A task first verifies the current behaviour
  (`docker compose stop` timing and the gateway's shutdown log) so the fix is evidenced, not assumed.
- **Bound.** `BUNDLEMCP_SHUTDOWN_DRAIN_SECONDS` (`Settings`, default 20) is passed to uvicorn as
  `timeout_graceful_shutdown`; `stop_grace_period: 30s` in compose leaves headroom over it.
- **Order.** On the lifespan's shutdown: a shutdown flag makes `/readyz` answer 503 and the MCP router refuse new POSTs
  with 503 + `Retry-After`; notification streams receive their end (GET streams close, listen streams send their
  completion result — the existing PROT-17 behaviour); in-flight calls get the drain window; at the deadline the
  registry cancels the remaining call handles, which `ToolCall` already reports as `cancelled` to metering; then the
  composition root closes its resources.

### D5. Fail fast through a stream-presence registry

A `StreamPresence` contract (`application/contracts/live_state/stream_presence.py`) with a Valkey adapter keeps
`bmcp:holder:{stream_id}` → replica id, written when a stream registers, refreshed with the stream's keep-alive (TTL
three keep-alive intervals) and deleted when it closes. `ClientRelay._roundtrip` checks presence before publishing; no
holder → `RelayRejected` at once, which the upstream sees as an error answer to its request. Notifications keep being
dropped silently.

*Alternative:* an acknowledgement signal from the holder with a short wait — one round-trip slower and a second
message type on the bus.

### D6. Postgres outage → 503

The SQLAlchemy unit-of-work adapter translates connection-level failures (`OperationalError`, `asyncpg` connection
errors, pool timeouts) into `StoreUnavailable` (`application/contracts/persistence/store_unavailable.py`). Handlers in
`api/` map it to 503 + `Retry-After`: a JSON-RPC error on the MCP edge (raised from `AdmissionGate.admit_caller`, after
the size gate and the parse, so the DoS ordering holds), a problem body on `/api/v1` and the OAuth routes. Credential
checks never translate an outage into 401.

### D7. Cache-off setting

`BUNDLEMCP_CONFIG_CACHE_DISABLED` makes `RuntimeConfig` read the store on every access. It is the only configuration
cache today (SES-22), so this one switch is the whole of it; any later cache must honour the same setting.

### D8. Integration topology

A compose overlay `deploy/docker-compose.replicas.yml` runs `gateway-a` and `gateway-b` behind Caddy (`reverse_proxy`
round-robin, active health check on `/readyz`, `lb_try_duration` so a dial to a stopping replica is retried on the other
— safe, since the request never reached it). The tests live in `tests/integration/`: a small load generator thread keeps
requests flowing on several sessions and records every status. The rolling update builds the image with a changed build
argument, then recreates `gateway-a`, waits for ready, recreates `gateway-b` (DEP-7). The upstream-restart test restarts
the `echo` container between two calls (needs SES-7 from the pooling change).

### Layer summary

| Piece | Layer |
|---|---|
| `SessionLifetime`, `SessionRecord` timestamps | `domain/sessions/` |
| `SessionSweeper`; `StreamPresence` and `StoreUnavailable` contracts | `application/` |
| Session store and presence adapters, activity index, sweep lease | `infrastructure/valkey/` |
| `StoreUnavailable` translation | `infrastructure/postgres/` |
| 503 handlers, shutdown refusal, presence check in the relay | `api/` |
| Sweeper start/stop, drain wiring, settings | `main/`, `apps/gateway/` |

## Risks / Trade-offs

- [The activity index grows with sessions that are never swept, e.g. `session_lifetime = 0`] → with `0` nothing is
  indexed; otherwise every swept or vanished id is removed.
- [A presence key outlives a crashed holder for up to three keep-alive intervals] → in that window a request waits as
  today, bounded by the call timeout.
- [503 during a Postgres outage turns clients away that a stale cache could have served] → recorded as the Open
  decision; the 503 is honest and retryable.
- [Two-replica integration tests are slower and flakier] → they run in the integration job only, with generous ready
  waits; the hermetic two-instance tests remain the fast guard.

## Migration Plan

Additive: no database migration, session records stay version 2. Operators who rely on the old shutdown behaviour see
an earlier exit; `stop_grace_period` in their own orchestration should exceed `BUNDLEMCP_SHUTDOWN_DRAIN_SECONDS`, which
the operations docs state.
