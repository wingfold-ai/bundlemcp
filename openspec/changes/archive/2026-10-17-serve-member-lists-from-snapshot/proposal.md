# Proposal

## Why

Issue [#147](https://github.com/wingfold-ai/bundlemcp/issues/147): connecting a client still wakes every member that
scales to zero. ADR-0043's capability filter skips a member only when its snapshot does not advertise `prompts` or
`resources`, but many servers advertise both without serving any. FastMCP, for one, advertises
`prompts: {listChanged: true}` and `resources: {listChanged: true}` even for a tool-only server. Clients such as
claude.ai send `prompts/list`, `resources/list` and `resources/templates/list` right after connecting, so every FastMCP
member is scaled up to answer with an empty list. A server that really has prompts or resources is woken the same way.

ADR-0043 names the fix as a deferred alternative: serve those lists from a snapshot taken at discovery.

## What Changes

- **Listing snapshots** (UPS-24, modified): a discovery probe already lists prompts and resources for curation. It now
  also lists resource templates, and stores each listing in full as the server listed it, with the `cacheScope` the
  server gave and whether the listing was complete. Discovery announces a listing that changed to the bundles' clients.
- **When a snapshot may be shared** (UPS-38, new): a new per-server setting `listing_snapshot` decides it, `auto` by
  default. Under `auto`, a listing the server marked `public` is shared and one marked `private` is not. A listing
  without a scope (servers older than revision 2026-07-28) is shared only when nothing the server is sent depends on
  the caller: no forwarded client headers, no identity header, and no per-user or delegated tokens. `shared` shares
  any listing not marked `private`, and `live` never shares. The override is needed because servers on the gateway's
  own network get the identity header by default (UPS-13), so `auto` would keep listing them live. The k3d setup in
  the issue is such a case.
- **Lists served from the snapshot** (BND-8, modified): `prompts/list`, `resources/list` and `resources/templates/list`
  answer each capable member from its snapshot when the snapshot is shareable and complete. They ask the member live
  only when it has no such snapshot. `prompts/get`, `resources/read`, `resources/subscribe` and `completion/complete`
  stay live. Curation (BND-37) applies unchanged.
- **List changes re-list the member** (PROT-10, modified): a member's `notifications/prompts/list_changed` or
  `notifications/resources/list_changed` re-discovers it before the bundles' clients are told. That refreshes the
  snapshot the clients will list next. The requirement already demands re-discovery for all three notifications, but
  the code did it only for tools.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `upstreams`: UPS-24 (listings stored in full, with templates, scope and completeness) and UPS-38 (added: when a
  snapshot is shared). The tool-discovery "Out of scope" note ("never served from the cache") is reworded on archive.
- `bundles`: BND-8 (lists served from the snapshot when it is shareable).
- `protocol`: PROT-10 (a prompt or resource list change refreshes the snapshot first).

## Impact

- **Resolves** issue #147.
- **Data:** an Alembic migration adds a `member_listings` table, one row per server and listing kind. Servers
  discovered before the migration have no snapshot and are listed live until their next discovery. An explicit refresh
  (`:refresh-tools`) or the periodic refresh fills the snapshot.
- **Code:** `domain/servers/` (the listing entity and its shareability rule), the probe contract and FastMCP adapter
  (paginated listing that keeps `cacheScope`), `DiscoveryService`, `UpstreamNotificationRouter`, `MemberFanout` and
  the three list handlers. Repositories in Postgres and in memory.
- **API:** `listing_snapshot` on the server upsert and read DTOs and in the configuration document (export, import,
  bootstrap); regenerate `apps/web/openapi.json` and `apps/web/types/api.d.ts`. The upstream registration form and
  detail page show the setting.
- **Docs:** a new ADR (ADR-0059) records serving member lists from the discovery snapshot. It amends ADR-0043 and
  ADR-0056, whose "served lists stay live" decision it reverses for the three list methods. Also
  `docs/manage/servers.md`, `docs/manage/bundles.md`, and arc42 §8 where it describes passthrough.
- **Not covered:** a per-identity cache of `private` listings (they stay live), and filling a missing snapshot from a
  live answer.
