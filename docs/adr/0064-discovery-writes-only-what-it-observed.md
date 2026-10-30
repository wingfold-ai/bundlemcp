# ADR-0064: Discovery writes only what it observed, and a delete waits for it

**Status:** accepted · **Date:** 2026-10-30 ·
**Amends:** [ADR-0063](0063-discovery-serialized-per-server-by-a-transaction-lock.md)

## Context

ADR-0063 serialized discoveries of one server with each other through `UnitOfWork.lock_server`. Deleting a server did
not take that lock, and a discovery stored the whole server entity it had read before probing. The repository stages an
entity and merges it at flush; the row it was read from is no longer in the session's (weak) identity map by then, so
the merge looks the row up, finds it deleted and inserts it again. CI caught it: an upstream deleted while the admin
UI's refresh probed it answered 404 once and then came back with the refresh's commit (E2E-03). Where the row still
existed, the same merge wrote back the name and configuration as they were before the probe, so a rename saved during a
discovery was undone.

## Decision drivers

- A deleted server stays deleted, on any replica, including one still running the previous release.
- An admin's write must not be undone by a discovery that started before it.
- An admin's write should not wait for a slow probe (ADR-0063), unless that wait is what keeps the store consistent.
- The application layer names contracts only (ADR-0033); the in-memory fakes keep the contract's meaning.

## Decision

- **Discovery writes only what it observed.** `ServerObservations` (domain) names the fields a probe or a live call
  finds out: capabilities, negotiated revision, health, last error, connection state, last discovery time.
  `ServerRepository.record_observations(server_id, observations)` writes them onto the stored server with a single
  `UPDATE … WHERE id`, never an insert, and reports whether a server was there. Discovery records them on every path,
  before it caches tools, prompt and resource entries or listings; when the server is gone it reports "server not
  found" and commits nothing. Live-call health updates (`UpstreamHealth`) use the same write.
- **Deleting a server takes the server lock.** `ServerService.delete` takes `lock_server` before deleting, so it waits
  for a discovery already running and a discovery that starts meanwhile waits for it and finds no server. This is the
  one admin write that waits behind a probe.
- **Rename and upsert do not take the lock.** Discovery no longer writes a server's name or configuration, so it cannot
  undo them, and they keep ADR-0063's promise of not waiting for a probe.

## Alternatives considered

- **Only the update-only write, no lock on delete.** Correct on its own for current replicas: an update of a deleted row
  matches nothing, and one that runs first holds the row until its discovery commits. But a previous-release replica
  still merges the whole entity during a rolling update; it does take the lock, so only a delete that waits for it is
  safe against that replica. The lock also lets the refresh in flight report its real result.
- **Only the lock on delete, keeping the whole-entity write.** Fixes delete, but a rename or a configuration change
  saved during a probe is still overwritten, and any writer that forgets the lock can resurrect a server.
- **Make every repository's `add` refuse to insert an entity it had read.** Changes the meaning of `add`, an upsert,
  for every service, including `PUT`, whose create-or-update is intended.
- **Lock rename and upsert too.** Not needed once discovery writes only its observations, and it would make every
  configuration save wait up to a probe timeout.

## Consequences

- A delete of a server whose discovery is running answers once that discovery has committed: usually milliseconds,
  at most one probe timeout (60 s) for an upstream that never answers.
- A discovery or live call never re-creates a deleted server, never caches anything for one, and never reverts a
  rename or a configuration change.
- A live call's health update writes the other observed fields as it read them; a discovery committing in that window
  (one Valkey round trip) can see its capability snapshot replaced until the next probe, as before with the whole row.
