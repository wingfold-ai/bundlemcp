# Proposal

## Why

Deleting an upstream while a discovery of it is running brings the upstream back. CI's integration job on PR #175
(gateway-1, 2026-10-30 14:14:34–35) shows the sequence: the admin UI's refresh
(`POST /upstreams/e2e-echo:refresh-tools`) starts a discovery; while it probes, `DELETE /upstreams/e2e-echo` answers 204
and a `GET` answers 404; the refresh then finishes (200, 251 ms) and stores the server it read before the probe, so the
next `GET` answers 200 and the list shows the row again. Playwright E2E-03 ("deleting the server removes it from the
list") failed on it.

The per-server lock that UPS-39 added serializes discoveries with each other only; deleting a server does not take it.
And a discovery stores the whole server it read before probing, which re-creates a row that is gone and overwrites
anything an admin saved meanwhile, such as a rename.

## What Changes

- Deleting an upstream waits for a discovery of it that is already running, and a discovery that starts while a delete
  is running waits for the delete and then finds no server. A deleted upstream stays deleted.
- A discovery stores only what it found out — capabilities, negotiated revision, health, connection state, last
  discovery time — onto the server as it is stored now. It never re-creates a server that has been deleted, and stores
  no tools, prompt or resource entries or listings for one; it reports "server not found" instead.
- A rename or configuration change saved while a discovery runs is kept, since the discovery no longer writes the
  server's name or configuration back. The same holds for the health a live call records.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `upstreams`: adds UPS-40 (a discovery never undoes a concurrent change to its server: a deleted server stays deleted,
  a rename or configuration change is kept).

## Impact

- **Gateway**: `ServerService.delete` takes the server lock (`UnitOfWork.lock_server`) before deleting.
  `ServerRepository` gains `record_observations`, an update of the probe-owned fields that never inserts and reports
  whether the server still exists; `DiscoveryService` and `UpstreamHealth` write through it instead of storing the
  whole entity. A new domain value object, `ServerObservations`, names those fields. No migration, no setting, no API
  shape change.
- **Tests**: hermetic tests on the in-memory fakes and sqlite (a delete, a removal behind the lock's back and a rename
  during a stalled probe), and a replica integration test that deletes an upstream while it is being refreshed.
- **Docs**: `manage/servers.md` (Deleting, Tools and health).
- **ADR**: adds ADR-0064, amending ADR-0063: a delete waits for a discovery in flight, and discovery writes only what
  it observed.
