# ADR-0063: Discovery is serialized per server by a transaction-scoped lock

**Status:** accepted · **Date:** 2026-10-30 ·
**Amended by:** [ADR-0064](0064-discovery-writes-only-what-it-observed.md)

## Context

A discovery reads a server's cached tools, prompt and resource entries and listings, probes the upstream with its
transaction open, and stores the difference. Nothing stopped two discoveries of one server from running at once: saving
an upstream schedules a background probe, and a "refresh tools" right after it runs a second. Both read an empty cache
and both inserted the same tools; the loser broke `uq_tools_server_name`. When the loser was the refresh request, the
`IntegrityError` left the request unhandled, so the gateway answered 500 and closed the connection. The browser suite
hit this intermittently (E2E-20, `ECONNRESET`). Two replicas, each running the periodic refresh or a refresh request,
can collide the same way.

## Decision drivers

- Any replica serves any request (ARC state model): the fix has to hold across processes.
- An admin's write to a server must not wait for a slow probe of it.
- The application layer names contracts, not drivers (ADR-0033); the in-memory fakes keep the contract's meaning.
- No new state to recover after a crash.

## Decision

- **A lock in the unit of work.** `UnitOfWork.lock_server(server_id)` waits until no other unit of work holds the
  server, then holds it until this one commits or rolls back. `DiscoveryService.discover` takes it before it reads
  anything, so a second discovery of the same server waits and then compares against what the first stored.
- **Postgres: a transaction-level advisory lock.** `pg_advisory_xact_lock` on 64 bits of the server's UUID. Postgres
  releases it at commit, rollback or a lost connection; every replica shares the database, so it holds fleet-wide.
  Only parties that ask for the lock wait; reads and writes of the server row do not.
- **sqlite and the in-memory fakes: a per-server `asyncio.Lock`.** sqlite here is the hermetic tests' single-process
  database and has no lock a second transaction could wait on; the fake hands one unit of work to every caller, so its
  lock belongs to the task that took it and lasts until that task leaves its outermost unit of work.
- **A collision that still happens is a 409.** The unit-of-work factory turns an `IntegrityError` into `StoreConflict`
  (an application contract, beside `StoreUnavailable`), which the API answers 409 with a retryable message, or a
  JSON-RPC error on an MCP path. Services that check a uniqueness rule up front keep their own `ConflictError`
  messages; this is the backstop for the race between such a check and the commit.

## Alternatives considered

- **`SELECT … FOR UPDATE` on the server row.** Serializes discovery as well, but holds the row for the whole probe (up
  to a minute), so an admin's `PUT /upstreams/{name}` would wait behind a slow upstream.
- **Upsert `ON CONFLICT (server_id, name)` in the tool repository.** Fixes one table: member entries and listings have
  the same race, and the change count and invalidations would still come from a stale read.
- **A Valkey lock (`SET NX PX`), as the upstream token refresher uses.** Fleet-wide too, but needs a TTL longer than the
  probe timeout, renewal or a crash window, and polling to wait. A lock that lives and dies with the transaction it
  protects cannot drift from it.
- **A per-server lock in `DiscoveryService`.** Holds on one replica only.

## Consequences

- Concurrent triggers of one server's discovery run one after another; a refresh may wait up to one probe timeout for a
  background probe of the same server, and then reports a fresh result. Different servers still probe in parallel.
- The waiting discovery holds a pooled database connection, as the probe already does while its transaction is open.
- An integrity violation anywhere behind a unit of work answers 409 instead of 500; it is logged as `store.conflict`
  with the constraint's name, never a value.
- During a rolling update a replica on the previous release does not take the lock; a collision with it is answered
  409 by the new replica.
