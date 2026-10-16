# Design

## Context

See [proposal.md](proposal.md). Today `DiscoveryService` (application) probes through `UpstreamProbe`. When a member's
capabilities advertise prompts or resources, the FastMCP adapter also lists them and keeps name, title and description
per entry as `MemberEntry` rows, for curation only (ADR-0056). Serving goes through `MemberFanout`
(`api/mcp/dispatch/handlers/member_fanout.py`). Its `merged(...)` asks every capable member live, then de-duplicates
and curates each entry through a `present` callback. `BundleView` is rebuilt per request in the admission
`UnitOfWork`, which every method shares, so anything added to it is paid for by `tools/call` as well.
`UpstreamNotificationRouter` re-discovers a member on a tools list change. On a prompt or resource list change it
only announces to the member's bundles.

## Goals / Non-Goals

**Goals:**

- Connecting a client and listing tools, prompts, resources and templates contacts no member whose listings are
  shareable.
- A client sees exactly what the member listed at its last discovery: every field, in the member's order.
- Behaviour for members whose lists may depend on the caller does not change: they are listed live, with the caller's
  headers.

**Non-Goals:**

- A per-identity cache of `private` listings, with its own `ttlMs` expiry. Such members are listed live as today.
- Filling a missing snapshot from a live answer on the request path. Snapshots are written by discovery only.

## Decisions

### One snapshot row per server and listing kind, separate from the curation entries

`MemberListing` (domain, `domain/servers/`): server id, kind (`ListingKind`: `prompts`, `resources`,
`resource_templates`), `entries` (a list of JSON objects in wire form, as the server listed them), `cache_scope`
(`public`, `private` or None), `complete`, `listing_hash`, `listed_at`. Its row class `MemberListingRow` lives in
`infrastructure/postgres/rows/`, with a unique `(server_id, kind)` and a cascade on server delete. Migration 0016 adds
the table. `MemberListingRepository` (application contract) is reached from the `UnitOfWork`, with Postgres and
in-memory adapters.

*Alternative:* add the full definition to `MemberEntry`. Rejected for three reasons. Curation entries are kept stale
when they vanish, so the served set would need a staleness filter. Order would need a position column that rewrites
every row when one entry is inserted at the front. And templates are not curated. One row per listing is one write
when it changes, none when it does not (hash gate), and one indexed read per kind on serving.

### The sharing rule is a domain property

`MemberListing.shareable_for(server)` returns False for an incomplete listing. Otherwise it follows `cache_scope`:
`public` is shareable and `private` is not. Without a scope it falls back to `server.is_identity_free`, the property
upstream session pooling already uses to decide that one session may serve any caller (ADR-0054). A server that
forwards headers, is sent the caller's identity, or authenticates per user or per caller is listed live unless it said
`public`.

### A per-server `listing_snapshot` setting overrides the rule

`ListingSnapshotMode` (domain, `auto` | `shared` | `live`) is a field on `McpServer`, with a column added by the same
migration and defaulting to `auto`. It appears on the upsert DTO as optional, keeps the stored value when omitted
(like `protocol_mode`), and is carried by `ServerRead`, the export document and bootstrap. It is not a discovery input
(ADR-0043), because it changes how a listing is served, not what is probed. `shareable_for` reads it first: `live` is
never shareable; `shared` is always shareable, because an SDK may mark every result `private` by default (the MCP
Python SDK does on revision 2026-07-28); `auto` applies the rule above.
The registration form gains a select for it, and the upstream detail page shows it.

*Alternative:* treat the identity header as harmless and leave it out of the rule. Rejected because the header exists
so an upstream on the gateway's network can trust who is calling, and it may filter on it. Only the operator knows
that it does not.

### The probe reads listings page by page to keep `cacheScope`

`FastMcpUpstreamProbe` calls `list_prompts_mcp`, `list_resources_mcp` and `list_resource_templates_mcp` with
`cache_mode="bypass"` and follows `nextCursor`. It stops at the 500-entry bound (`MEMBER_LISTING_LIMIT`) or on a
repeated cursor. The listing's scope is `private` if any page says so, `public` only if every page says so, and None
otherwise. `ProbeResult` gains `listings: list[ProbedListing]` (kind, entries, scope, complete), one per kind listed.
A kind missing from it was not advertised or failed to list, and its stored snapshot is left alone. The curation
entries (`prompts`, `resources`) are derived from the same pages, so a probe sends each list request once.

### Discovery writes, compares and announces

`DiscoveryService.discover` upserts each probed listing with `sync_member_listing` (domain), hash-gated on the
canonical JSON of entries, scope and completeness. When a prompt snapshot changed it raises a `bundle_prompt`
invalidation for every bundle the server is an enabled member of. A resource or template snapshot raises a
`bundle_resource` invalidation. The `ListChangedNotifier` turns these into `notifications/prompts/list_changed` and
`notifications/resources/list_changed`, as for bundle-owned content. The first discovery after the migration writes a
snapshot where there was none and therefore announces once, which is harmless.

### Serving: snapshot first, live fallback, same merge

`MemberListingReader` (application, `application/serving/`) takes the `UnitOfWorkFactory`, like
`BundleContentReader`. It returns the shareable snapshots of the given members for one kind in one short unit of work,
opened only by the three list handlers. `MemberFanout.merged` gains a `listing: ListingKind` argument. For each
capable member it uses the entries of a shareable snapshot, or else calls the member live as today. Both feed the same
de-duplication and `present` callback, so prefixing, curation (BND-37) and the bundle-URI shadowing are unchanged.
`each` and `first` stay live for `prompts/get`, `resources/read`, `resources/subscribe` and completions.

*Alternative:* load the snapshots into `BundleView`. Rejected because every method, `tools/call` included, would then
pay for a read only three methods use.

### A member's prompt or resource list change re-discovers it

`UpstreamNotificationRouter` treats `notifications/prompts/list_changed` and `notifications/resources/list_changed` as
it treats a tools list change. Behind the same replica gate it runs `discovery.discover(server.id)`. That rewrites the
snapshot and, when the listing changed, announces to clients through the invalidation above. The router no longer
announces separately. A notification whose re-listing finds nothing changed therefore tells no client to list again,
because nothing they would be served has changed.

### ADR

ADR-0059 records the decision. It amends ADR-0043 (the deferred alternative is taken) and ADR-0056, whose decision
that served lists stay live it reverses for the three list methods.

## Risks / Trade-offs

- **Staleness without notifications.** A member whose listing changes without sending `list_changed`, or whose
  notification goes unheard because upstream pooling is off, is served the old listing until its next discovery.
  Before this change such a member's live answer was always current. The periodic refresh (UPS-23) and the explicit
  refresh bound the gap; the ADR and `docs/manage/servers.md` say so.
- **Existing deployments.** Servers discovered before the upgrade have no snapshot and are listed live until their next
  discovery. Unchanged upserts do not probe (ADR-0043), so an operator runs `:refresh-tools` once or relies on the
  periodic refresh. The release note says so.
- **Down members are listed.** A member that is down still contributes its last listing to `prompts/list`, where the
  live fan-out skipped it. Its `prompts/get` fails as before. This matches how its tools stay listed while it is down.
- **Size.** At most 500 entries per kind and server are stored as JSON. A listing longer than that is marked
  incomplete and listed live, which is the behaviour before this change.
