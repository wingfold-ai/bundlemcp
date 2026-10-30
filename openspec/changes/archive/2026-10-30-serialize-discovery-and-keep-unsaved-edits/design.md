# Design

## Context

See proposal.md for the three races and how they were found. The constraints that shape the fixes:

- **Discovery runs in one unit of work** (`DiscoveryService.discover`, application layer): it reads the server, probes
  it (up to `PROBE_TIMEOUT_SECONDS`, 60 s) with the transaction already open, diffs the cached tools, prompt and
  resource entries and listings against what the probe saw, stages the difference and commits. Two of these for one
  server interleave freely today; nothing in the store stops both from inserting the same new rows except the
  uniqueness constraints, and the loser's `IntegrityError` propagates out of the request unhandled.
- **Any replica serves any request** (ARC state model): a fix that only holds within one process does not hold.
- **Layering** (ADR-0033): `application/` names contracts only; infrastructure implements them, and the in-memory
  fakes must keep the contract's meaning so use-case tests stay honest.
- **The hermetic sqlite database is one shared connection** (`packages/bundlemcp/tests/conftest.py`), so it has no
  transaction isolation between two units of work and no lock a second one could wait on.
- In the admin UI, every card copies its resource into local refs with a `watch(..., { immediate: true })` that
  overwrites them on every read. `useEditableRows` (tool curation) already solves this for tables by keeping a row the
  admin changed; `MemberEntryCuration.vue` carries a hand-copied version of the same loop.

## Goals / Non-Goals

**Goals:**

- Discoveries of one server never overlap, across replicas, without blocking admin writes to the server.
- No integrity violation reaches a client as a 500 or a dropped connection.
- One reseeding rule in the UI, written once, used by every form that copies gateway data.
- Pausing the live log is final until resume.

**Non-Goals:**

- Optimistic concurrency between two admins editing the same resource (last write wins, as today).
- Making the admin UI notice that the gateway's value changed under an edit (no conflict banner).
- Coalescing a refresh into a discovery already running (the refresh waits, then probes itself, so its result is
  fresh).

## Decisions

### 1. Serialize per server with a transaction-scoped lock in the unit of work

`UnitOfWork.lock_server(server_id)` (application contract, `application/contracts/persistence/unit_of_work.py`):
waits until no other unit of work holds that server, then holds it until this unit of work commits or rolls back.
`DiscoveryService.discover` calls it first, before it reads the server, so the second discovery reads the cache the
first committed and finds nothing new to insert.

- **Postgres** (`infrastructure/postgres/sqlalchemy_unit_of_work.py`): `SELECT pg_advisory_xact_lock(:key)` with a
  64-bit key derived from the server's UUID. Postgres releases it at commit, rollback or a dropped connection, so no
  lease, TTL or crash recovery is needed, and it holds across replicas because they share the database.
- **sqlite** (hermetic tests only; production requires Postgres): a process-local `asyncio.Lock` per server, held by
  the unit of work and released by its commit, rollback or close. sqlite in this repository is a single process, so a
  process lock is the whole truth there.
- **In-memory fake** (`infrastructure/memory/in_memory_unit_of_work.py`): the same per-server `asyncio.Lock`, owned by
  the task that took it, since the fake hands one shared unit of work to every caller.

Alternatives considered:

- **`SELECT … FOR UPDATE` on the server row.** Serializes discovery just as well, but the row stays locked for the
  whole probe, so an admin's `PUT /upstreams/{name}` would wait up to a minute behind a slow upstream. The advisory
  lock serializes only the parties that ask for it.
- **Upsert `ON CONFLICT (server_id, name)` in the tool repository.** Fixes the tool table only. Member entries and
  listings have the same race; the change count (`changed`) and the invalidation events would still be computed from a
  read that is already stale; and the generic repository flush would need a dialect-specific path per table.
- **A Valkey lock (`SET NX PX`) as the token refresher uses.** Works across replicas, but needs a TTL longer than the
  probe timeout, renewal or a crash window, and polling to wait. The thing being protected is a database transaction;
  a lock that lives and dies with that transaction cannot drift from it.
- **A per-server `asyncio.Lock` in `DiscoveryService`.** Fixes one replica only.

The wait holds a pooled connection, as the probe already does today while the unit of work is open. A waiter waits at
most one probe timeout plus the other discovery's writes.

### 2. Integrity violations become `StoreConflict`, answered 409

`application/contracts/persistence/store_conflict.py` declares `StoreConflict`, beside `StoreUnavailable`. The
SQLAlchemy unit-of-work factory translates an `IntegrityError` escaping a unit of work into it, in the same place it
translates connection failures into `StoreUnavailable`. `api/http/store_conflict_handler.py` answers it 409 with a
problem body ("collided with a concurrent change; retry"), or a JSON-RPC error on an MCP path, and is registered in
`main/app.py` beside the 503 handler. Services that already check a uniqueness rule up front (`ConflictError`) keep
their specific messages; this is only the backstop for the race between check and commit. The in-memory tool
repository refuses a second tool with the same server and name with the same exception, so the fakes keep the
constraint the use-case tests rely on.

### 3. One reseeding rule in the UI: `useEditableField` beside `useEditableRows`

`apps/web/app/composables/useEditableField.ts` returns a ref filled from a getter. When the getter's value changes it
takes the new value only if the ref still equals what it was last filled with (compared as JSON, so arrays and row
lists compare by content); otherwise it keeps the edit. In both cases it remembers the new value as the last fill, so
once a save comes back the field is unchanged again. `useEditableRows` uses the same comparison per row; the
hand-copied loop in `MemberEntryCuration.vue` and the settings page move onto `useEditableRows`.

Per-field rather than per-form: a card with several fields keeps the one the admin is typing in and still shows a
change to the others. Cards that keep transient input which is never filled from the gateway (new static header
values, a client secret) clear it after a successful save instead of on every read.

The inspector's argument form (`ToolArgumentsEditor.vue`) is not gateway data being edited, but it had the same bug
shape: it reset whenever the tool object was replaced. It now resets only when the tool's name or input schema
changes.

### 4. Pause bumps the live log's load generation

`togglePause()` increments `generation` when it pauses, which is how `restart()` already drops a load that answers
after the filters changed. A load in flight at pause time is discarded; resuming finds no position (`lastId` is empty)
and loads afresh for the current filters, as it already does for a page paused before anything was shown.

### 5. Tests wait for the state they assert

- E2E-19 waits for the curation PUT's response before reading the API (the field showing the typed value is not
  evidence the save landed).
- E2E-36 waits for the filtered backlog request to answer before asserting `live`, so the state it sees is the
  filtered stream's and not the one before the debounce fired.

## Risks / Trade-offs

- [A slow upstream delays a refresh of the same server by up to one probe timeout] → The request waits rather than
  failing; the alternative was a 500. Different servers are unaffected.
- [Advisory-lock keys are 64 bits of a UUID; two servers could share a key] → They would only serialize with each
  other, never corrupt anything.
- [The generic 409 also covers integrity errors that are bugs, not races] → They answered 500 before and were just as
  unrecoverable for the client; the handler logs them at warning with the path, so they stay visible.
- [`useEditableField` compares by JSON] → Only plain data is bound to these fields; a number input that yields a number
  where a string was filled counts as an edit, which keeps the admin's value, the safe side.

## Migration Plan

No schema change, no setting. Replicas running the old code do not take the lock; during a rolling update a discovery
on an old replica can still collide with one on a new replica, and the new replica answers that collision with 409.
