# Design

## Context

See proposal.md for the race and the CI evidence. The state this change starts from (the archived change
`serialize-discovery-and-keep-unsaved-edits`, ADR-0063):

- `DiscoveryService.discover` (application layer) opens one unit of work, takes `uow.lock_server(server_id)`, reads the
  server, probes it with the transaction open (up to 60 s), mutates the entity it read and stages it with
  `uow.servers.add(server)`, then stages tools, member entries and listings and commits. The failure and
  "account required" paths stage the server the same way.
- `NamedResourceService.delete` (used by `ServerService`) reads the server by name and deletes it in the request's own
  unit of work. It does not take the lock, so it runs while a discovery probes.
- The SQLAlchemy repository stages an entity and `session.merge`s it at flush. The session's identity map holds rows
  weakly, and the repository keeps only the entity, so by the time a discovery flushes the row it read is usually gone
  from the map: `merge` selects by primary key, finds nothing (the delete committed), and inserts. That insert is the
  resurrection; the tools, entries and listings staged after it then satisfy their foreign keys. Where the row is still
  there, the merge writes every column of the entity read before the probe, so a rename or configuration change
  committed meanwhile is reverted too.
- `UpstreamHealth.failed`/`succeeded` (live calls) read a server, update the failure streak in Valkey and save the
  whole entity with the same `add`; a smaller window, the same shape.

## Goals / Non-Goals

**Goals:**

- A deleted server stays deleted, whatever a discovery that read it earlier does afterwards, on any replica.
- A discovery never overwrites the server's name or configuration with the copy it read before probing.
- Delete and discovery of one server do not interleave when both run current code.

**Non-Goals:**

- Optimistic concurrency between two admins editing one server (last write wins, as before).
- Locking rename or upsert against discovery: once discovery writes only what it observed, neither can be undone by
  it, and they must not wait behind a probe (ADR-0063's driver).
- Cascading deletes in the in-memory fake: the database cascades, the fake does not, as before.

## Decisions

### 1. Delete takes the server lock (application layer)

`ServerService.delete` reads the server, calls `uow.lock_server(server.id)`, then deletes through the inherited
`NamedResourceService.delete`, which reads by name again. A delete that arrives while a discovery probes waits for that
discovery to commit, so the refresh answers with its full result and the delete then removes the server and (by cascade)
everything the discovery stored. A discovery that starts while the delete holds the lock waits, reads no server and
reports "server not found". Reading by name again after the wait keeps the delete honest if the server was renamed
meanwhile: it deletes what is named that now, or nothing.

Rename and upsert do not take the lock (see Non-Goals): with decision 2 a discovery cannot undo them, and making them
wait up to a probe timeout is the cost ADR-0063 avoided.

Alternative considered: **no lock on delete, rely on decision 2 alone.** It is enough for correctness: on Postgres a
discovery's update of a deleted row matches nothing, and an update that runs first holds the row until the discovery
commits, so the delete then cascades. But a discovery on a replica still running the previous release (during a rolling
update) takes the lock and still writes the whole row; only the lock keeps that replica from resurrecting a server
deleted on a new one. It also lets the refresh in flight answer its real result instead of "not found".

### 2. Discovery writes only what it observed, and only onto a server that exists

- **Domain**: `ServerObservations` (`domain/servers/server_observations.py`), a frozen value object with the fields a
  probe or live call finds out: `capabilities`, `protocol_version`, `health_status`, `last_error`, `connection_state`,
  `last_discovered_at`. `McpServer.observations` returns it, beside `discovery_inputs`, which names the configuration a
  probe depends on.
- **Application contract**: `ServerRepository.record_observations(server_id, observations) -> bool` writes those
  fields onto the stored server and returns whether there was one. It never inserts.
- **Postgres/sqlite adapter**: one `UPDATE mcp_servers SET … WHERE id = :id`, through the repository's existing
  `update_where`; one row changed means the server exists. Under Postgres' read-committed isolation an update of a row a
  concurrent transaction deletes waits for it and then matches nothing.
- **In-memory fake**: sets the fields on the stored entity if the id is present.
- **`DiscoveryService`**: every path (success, failure, account required) records the observations instead of staging
  the entity, and the success path does so *before* it stages tools, entries and listings. When nothing was recorded
  the discovery logs `discovery.server_gone`, returns `DiscoveryResult(error="server not found")`, and leaves the unit
  of work uncommitted, so nothing staged is written. Health success is applied before the record, as part of it.
- **`UpstreamHealth`**: `failed` and `succeeded` record observations instead of saving the entity.

Alternatives considered:

- **Re-read the server under the lock after the probe.** Narrows the window but does not close it for a writer that
  does not take the lock, and the merge still writes every column back.
- **Make the generic repository refuse to insert an entity it had read.** Fixes every service at once but changes the
  meaning of `add` (an upsert) for all of them, including `PUT`, whose create-or-update is intended.
- **`SELECT … FOR UPDATE` on the server row for the whole discovery.** Rejected in ADR-0063: an admin's write would
  wait behind a slow probe.

## Risks / Trade-offs

- [A delete waits up to one probe timeout (60 s) behind a discovery of the same server] → Deleting an unreachable
  server whose probe hangs is slow, not wrong; the admin UI shows the request pending. A failing probe usually fails
  fast (refused connection, DNS), and an upstream that never answers is bounded by the timeout.
- [A health update from a live call writes the observed fields it read, including capabilities] → The window is one
  Valkey round trip; before this change it wrote the whole row in the same window. A discovery committing in between
  could have its capability snapshot replaced by the previous one until the next probe.
- [A discovery that finds its server gone reports "server not found" with status 200 on the refresh route] → This is
  the existing answer for a server that is gone when the discovery starts.

## Migration Plan

No schema change, no setting. During a rolling update, a discovery on a previous-release replica still writes the
whole row, but it takes the lock, which a delete on a new replica now waits for.
