# Proposal

## Why

The browser suite fails intermittently in CI, and the failures trace back to three races in the product, not to the
tests alone. Each was reproduced against a local stack on `main` (E2E-40 failed 3 of 15 runs with `--repeat-each`):

- **An edit in progress is overwritten by a refetch.** The bundle meta card, and every other card that copies a
  resource into form fields, reseeds the fields whenever the resource is read again. Any refetch — another card's
  action invalidating the same query, say — throws away what the admin typed, and the save then sends the stale value
  (E2E-40). The tool and entry curation tables already keep an edited row; the cards and the endpoint and settings
  pages do not.
- **Two discoveries of one server insert the same tools.** Saving an upstream schedules a background probe; a
  "refresh tools" right after it probes the same server concurrently. Both read an empty tool cache, both insert, and
  the loser violates the `(server, tool name)` uniqueness rule. When the loser is the refresh request, the integrity
  error escapes as an unhandled exception: the gateway answers 500 and drops the connection (E2E-20, `ECONNRESET`).
  Two replicas can collide the same way.
- **Pausing the live log does not stop it.** A pause that lands while the page is still loading the backlog for a
  changed filter lets that backlog arrive afterwards, so rows appear on a paused page (E2E-36).

A fourth flake, E2E-19, is the test reading the API before the UI's save had landed; it is fixed in the test.

## What Changes

- The admin UI keeps an edit in progress when the data behind a form is read again: a field (or a table row) takes the
  gateway's new value only while it still holds the value it was last filled with. Bundle meta, upstream
  configuration, upstream OAuth client, endpoint configuration, the settings page and the prompt/resource curation
  table all follow the one rule the tool curation table already follows, through one shared composable. The
  inspector's argument form is reset only when the tool itself changes, not when its listing is read again.
- Discoveries of one server are serialized across every replica: a discovery waits until any other discovery of the
  same server has committed, then reads the cache that one left. Concurrent triggers no longer store a tool twice, and
  a refresh never fails because a background probe of the same server ran meanwhile.
- A write that collides with a concurrent write on a uniqueness rule answers 409 with a retryable message instead of
  an unhandled 500 that closes the connection.
- Pausing the live log discards a backlog load still in flight, so nothing is added to a paused page.
- The Playwright scenarios E2E-19 and E2E-36 wait for the state they assert on: the save's response, and the filtered
  stream rather than the one before the filter applied.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `admin-ui`: adds UI-14 (an edit in progress survives a refresh of the data behind it).
- `upstreams`: adds UPS-39 (discoveries of one server never overlap).
- `management`: modifies MGMT-6 (a write that collides with a concurrent one answers 409, not 500).
- `operations`: modifies OPS-15 (nothing reaches a paused live log page, including a load already in flight).

## Impact

- **Gateway**: `UnitOfWork` gains `lock_server` (application contract); the SQLAlchemy unit of work implements it with
  a transaction-scoped Postgres advisory lock (a process-local lock on sqlite), the in-memory fake with a per-server
  `asyncio.Lock`. `DiscoveryService.discover` takes the lock before it reads the server. A new contract exception,
  `StoreConflict`, is raised by the unit-of-work factory for an integrity violation and answered 409 by a handler next
  to the `StoreUnavailable` one. No migration, no new setting, no API shape change.
- **Admin UI**: a new `useEditableField` composable beside `useEditableRows`; the cards and pages listed above use
  them. `logs.vue` bumps its load generation on pause.
- **Tests**: hermetic concurrency tests for discovery on sqlite and on the in-memory fakes, an API test for the 409,
  a cross-replica integration test that runs a refresh on each replica at once, Vitest cases for the composable, and
  the two corrected Playwright scenarios.
- **ADR**: adds ADR-0063, discovery serialized by a transaction-scoped lock and integrity conflicts answered as 409.
