# Design

## Context

See [proposal.md](proposal.md) for the motivation. The relevant code today:

- `domain/servers/tool_sync.py` (`sync_tools`) stages every seen tool, moving `last_seen_at` on each, and counts only
  new and changed definitions. Vanished tools are simply not staged.
- `application/serving/bundle_view_loader.py` builds the `BundleView` that backs both `tools/list` and `tools/call`
  from every cached tool of the enabled members; nothing filters stale tools.
- `application/management/bundle_service.py` checks override names with `CurationRepository.override_name_taken`,
  which compares against other overrides only. `add_member` and `ServerService.rename` check nothing about names.
- Memberships (`domain/bundles/bundle_server.py`) carry no position; `BundleService._members` sorts by server name and
  `BundleView.servers` is a name-keyed dict, which is what the member fan-out iterates.
- `apps/web/app/pages/bundles/[name].vue` keeps only `enabled`, `override_name` and `override_title` per row, and
  `saveCuration` sends `override_description: null` and no `override_annotations`. The PUT replaces the whole curation
  record, so every save wipes both.

## Goals / Non-Goals

**Goals:**

- One definition of "stale" (not listed by the latest successful discovery), computed in `domain/`, used by the view
  composition, the management DTOs and prune.
- The common discovery run writes no tool row (subject to the UPS-18 open decision in the proposal).
- Name collisions between override names and prefixed names are impossible to create through any write path.

**Non-Goals:**

- Partial (PATCH) curation updates. The PUT stays a full replacement; the UI is fixed to send the full record.
- Editing input schemas (TM out of scope).
- Pruning automatically. Deletion stays an explicit admin action.

## Decisions

### Stale is a marker set on transition, not a moving timestamp

`Tool` gains `stale_since: datetime | None` (domain entity, row class, migration). `sync_tools` compares the probe with
the cache and stages a tool only when it is new, its hash changed, it vanished (`stale_since` set to now) or it
reappeared (`stale_since` cleared). An unchanged run stages nothing, which is what UPS-18 asks for. `changed` counts all
four kinds, so `DiscoveryService._announce` fires for vanish and reappear too (BND-7).

`last_seen_at` stays as a published field but is derived rather than written per run: for a non-stale tool it is the
server's last successful discovery time (a new `McpServer.last_discovered_at`, one row write per run, which the server
row already gets for `connection_state`); for a stale tool it is `stale_since`. If the maintainers pick "batch" or
"amend" for UPS-18, `last_seen_at` stays a column and `stale_since` is added beside it; the staleness rule does not
change.

*Alternative:* derive staleness as `last_seen_at < server.last_discovered_at`. Rejected for the write-free option
because it still needs a per-tool write on every run; it is the natural rule under "batch".

### Stale tools are filtered where curation is applied

`present_tool` (domain) already returns `None` for a disabled tool; it also returns `None` for a stale one, so the same
`BundleView` excludes it from `tools/list` and from call resolution (BND-13 path, unknown-tool error, denied audit).
`BundleService.list_tools` (the curation view) keeps stale tools and reports `stale: true`; `catalogue_tools` drops
them because it shows what is served.

### Prune is a flag on the existing refresh

`POST /api/v1/upstreams/{name}:refresh-tools?prune=true` runs `DiscoveryService.discover(..., prune=True)`: after a
successful probe and sync in the same unit of work, it deletes the server's stale tools and their `BundleTool` rows (a
new `CurationRepository.delete_for_tools`), announces the server's bundles, and reports `pruned` in
`DiscoveryResult`. A failed probe returns before the prune. *Alternative:* a separate `:prune-tools` action that
deletes whatever is stale without probing. Rejected: it can prune on stale information, and the spec names the
operation "refresh & prune".

### Prefixed-name collisions are checked by a domain policy

A `PresentedNamePolicy` in `domain/bundles/` takes the bundle's members, their cached tools and the curation records
and answers "which tool already presents this name". It is used by `curate_tool` (override write), `add_member` (the
new member's prefixed names against existing overrides) and `ServerService.rename` (the renamed server's prefixed names
in every bundle it belongs to). Each raises `ConflictError` naming the colliding tool. The data is loaded through the
existing repositories in the service's `UnitOfWork`; no new query is needed beyond `tools.for_servers`.

Discovery cannot be refused, so a newly discovered upstream tool can still produce a prefixed name equal to an
existing override. The view composition resolves that deterministically: the override keeps the name, the newly
discovered tool is not served under it, and `bundle.presented_name_collision` is logged as a warning naming both.

*Alternative:* forbid `__` in override names, which makes them disjoint from prefixed names by construction and removes
every re-check. Rejected for now because existing overrides may already contain `__` (the migration would have to
rename them, a client-visible change); worth revisiting if the re-checks prove fragile.

### Member order is a position on the membership

`BundleServer` gains `position: int` (domain, row, migration backfilling positions in server-name order per bundle, so
behaviour is unchanged on upgrade). `add_member` appends (`max + 1`). A new action route
`PUT /api/v1/bundles/{name}/upstreams:order` takes `BundleMemberOrder {upstreams: list[ResourceName]}`, which must be a
permutation of the current members (422 otherwise), and rewrites positions in one unit of work, invalidating the
bundle. `MembershipRepository.for_bundle` returns memberships by position; `BundleView.servers` keeps insertion order
from that list (a `dict` preserves it), so the fan-out in `api/mcp/dispatch/handlers/member_fanout.py` follows it
without change beyond dropping any name sort. The bootstrap runner sets positions from the document's `upstreams` list.

*Alternative:* an optional `position` on the membership PUT. Rejected: moving one member means shifting others, and
two concurrent PUTs can produce duplicate positions; a whole-list reorder is atomic and idempotent (MGMT-6).

### The UI sends the full curation record

The page keeps every override per row (name, title, description, annotations as JSON text validated before save) and
`saveCuration` sends all of them. A component test asserts that saving after an API-set description keeps it.

## Risks / Trade-offs

- [A transiently flaky upstream that omits a tool on one probe hides it from clients until the next refresh] → Staleness
  needs a *successful* probe that omits the tool; UPS-23 refreshes every 30 minutes, and an explicit refresh restores it
  immediately. The curation is never lost.
- [Clients that cached a vanished tool get "unknown tool" instead of an upstream error] → That is the intended
  behaviour; `tools/list_changed` is sent when a tool goes stale (BND-7).
- [Prune deletes curation irrecoverably] → Only on explicit request, only after a successful probe; the UI confirms
  with the list of tools to be deleted.
- [Rename and member-add now fail where they succeeded before] → The 409 names the override, so the admin can rename or
  clear it first.

## Migration Plan

One Alembic revision: add `tools.stale_since` (nullable), `mcp_servers.last_discovered_at` (nullable) and
`bundle_servers.position` (backfilled per bundle in server-name order, then `NOT NULL`). Rollback drops the three
columns; nothing else depends on them. Existing vanished tools are not detectable at migration time, so they become
stale on the first successful discovery after the upgrade (at most one UPS-23 interval).
