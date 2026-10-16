## MODIFIED Requirements

### Requirement: UPS-24 Prompt and resource discovery
When a discovery probe reaches a server whose capability snapshot ([UPS-22](../upstreams/spec.md))
advertises `prompts`, the gateway SHALL also list its prompts. When the snapshot advertises `resources`, it SHALL also
list its resources and resource templates. Each listing is read to its last page and kept two ways:

- **For curation:** per entry, the prompt name or resource URI with its title and description, hash-gated like tools
  (UPS-18) and kept, not deleted, when they vanish (UPS-19). Resource templates are not curated.
- **As a listing snapshot:** the whole listing exactly as the server listed it, entry by entry and in its order, with
  the `cacheScope` the server put on the wire, if any, and whether the listing was complete. Endpoints serve lists from
  this snapshot when it may be shared (UPS-38, [BND-8](../bundles/spec.md)).

Neither holds prompt messages or resource content. The number of entries kept per server and kind is bounded; a longer
listing is cached truncated for curation, its snapshot is marked incomplete, and the truncation is logged. A listing
that fails leaves both as they were. A probe whose listings differ from the stored snapshots announces the change to
the clients of every bundle the server is an enabled member of, as prompt or resource list changes, the way the
member's own list-change notification is announced ([PROT-10](../protocol/spec.md)).

#### Scenario: Prompts are cached at discovery
- **WHEN** discovery succeeds against an upstream advertising `prompts` that lists prompts `daily` and `weekly`
- **THEN** both prompts are cached for the server with their titles and descriptions, and no prompt messages are stored

#### Scenario: The listing is stored as listed
- **WHEN** discovery succeeds against an upstream advertising `resources` that lists a resource with a MIME type and
  a resource template, across two pages
- **THEN** the stored snapshots hold both pages' entries in the server's order, each with every field the server
  listed

#### Scenario: A server without the capability is not asked
- **WHEN** discovery succeeds against an upstream whose snapshot does not advertise `resources`
- **THEN** the upstream receives no `resources/list` or `resources/templates/list` request

#### Scenario: A failed listing keeps the cache
- **WHEN** a later discovery of the same server fails before or while listing its prompts
- **THEN** the cached prompts and the prompt snapshot are unchanged

#### Scenario: A long resource listing is truncated observably
- **WHEN** an upstream lists more resources than the bound
- **THEN** only the bound is cached for curation, the resource snapshot is marked incomplete, and a warning naming the
  server is logged

#### Scenario: A changed listing is announced
- **GIVEN** a client holds an open stream on an endpoint of a bundle with member `docs`
- **WHEN** an explicit refresh of `docs` finds a resource that its stored snapshot does not have
- **THEN** the client receives `notifications/resources/list_changed`

## ADDED Requirements

### Requirement: UPS-38 Shared listing snapshots
A listing snapshot (UPS-24) SHALL be served to every caller of a bundle only when it is **shareable**. A server's
`listing_snapshot` setting decides how, and is `auto` unless set on write:

- **`auto`:** a listing the server marked `cacheScope: public` is shareable, and one marked `cacheScope: private` is
  not. A listing without a scope, as servers before revision 2026-07-28 send it, is shareable only when nothing the
  server is sent depends on the caller. That holds when the server forwards no client headers, is not sent the
  caller's identity, and authenticates neither per user nor with a token delegated per caller.
- **`shared`:** every listing is shareable, whatever scope the server gave. An operator chooses it for a server that
  is sent the caller's identity but lists the same for everyone, or one that marks every result `private` because
  that is its SDK's default on revision 2026-07-28.
- **`live`:** no listing is shareable, so the server is always asked.

An incomplete snapshot is never served. A server's `ttlMs` on a list result does not expire its snapshot; the snapshot
is replaced by the next discovery of that server ([UPS-17](../upstreams/spec.md), [UPS-23](../upstreams/spec.md),
[PROT-10](../protocol/spec.md)). The setting is part of the server's management API representation and of the
configuration document ([MGMT-9](../management/spec.md)); changing it does not probe the server.

#### Scenario: An identity-free server's listing is shared
- **GIVEN** a server with no forwarded headers, no identity header and a shared credential, whose prompt listing had
  no `cacheScope`
- **WHEN** its snapshot is checked for serving under `auto`
- **THEN** it is shareable

#### Scenario: A server sent the caller's identity is not shared
- **GIVEN** a server that forwards the caller's `Authorization` header, whose prompt listing had no `cacheScope`
- **WHEN** its snapshot is checked for serving under `auto`
- **THEN** it is not shareable

#### Scenario: The server's scope decides when it gave one
- **GIVEN** a server sent the caller's identity, whose listing was marked `cacheScope: public`, and an identity-free
  server whose listing was marked `cacheScope: private`
- **WHEN** both snapshots are checked for serving under `auto`
- **THEN** the first is shareable and the second is not

#### Scenario: An operator shares or refuses explicitly
- **GIVEN** a server sent the caller's identity header, whose listing was marked `cacheScope: private`
- **WHEN** its snapshot is checked under `shared`, and again under `live`
- **THEN** it is shareable under `shared` and not under `live`

#### Scenario: The setting round-trips
- **WHEN** an admin upserts a server with `listing_snapshot: shared` and later upserts it without the field
- **THEN** `GET /api/v1/upstreams/{name}` reports `listing_snapshot: shared` both times, and neither write probes the
  server for that field
