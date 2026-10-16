# ADR-0059: Members' prompt and resource lists are served from the discovery snapshot

**Status:** accepted · **Date:** 2026-10-17 · **Amends:** [ADR-0043](0043-contact-upstreams-only-with-a-reason.md),
[ADR-0056](0056-member-listings-cached-for-curation-only.md)

## Context

ADR-0043 kept a member that scales to zero asleep only when its capabilities snapshot does not advertise `prompts` or
`resources`. Issue #147 found that this rarely holds. FastMCP advertises both by default, even on a tool-only server,
and claude.ai sends `prompts/list`, `resources/list` and `resources/templates/list` right after connecting. So every
FastMCP member was scaled up to answer with an empty list, and so was any member that really has prompts or resources.
ADR-0043 named the fix as a deferred alternative: serve those lists from a snapshot.

ADR-0056 had since made discovery list prompts and resources for curation, but kept serving live. It rejected
serving from the cache because a client's view would then depend on discovery freshness.

Revision 2026-07-28 lets a server say who may share a list result (`cacheScope`). The MCP Python SDK sends
`private` unless the server author sets a scope. Older revisions send no scope.

## Decision drivers

- Connecting a client and listing everything wakes no member whose lists are the same for every caller.
- A listing that may differ per caller is never shown to someone else.
- What a client is served is what the member listed: every field, in its order.
- An operator can say what the gateway cannot infer.

## Decision

- **Discovery stores each listing in full.** When a member advertises the capability, the probe reads prompts,
  resources and resource templates to the last page and stores each as one `MemberListing`: the wire entries, the
  `cacheScope` the server put on the wire, and whether the listing fit the 500-entry bound. The write is hash-gated.
  A listing that failed keeps the stored one. A changed listing announces `prompts/list_changed` or
  `resources/list_changed` to the member's bundles. The curation entries of ADR-0056 come from the same pages.
- **A per-server `listing_snapshot` decides sharing.**
  - `auto`, the default: a listing marked `public` is shared and one marked `private` is not. An unscoped listing is
    shared only when the server is identity-free: no forwarded headers, no identity header, no per-user or delegated
    token. This is the property upstream session pooling already uses (ADR-0054).
  - `shared`: every listing is shared, whatever scope the server gave.
  - `live`: nothing is shared.
  - An incomplete listing is never shared.
- **The three list methods answer from shareable listings.** They ask a member live only when it has none. Reading the
  listings costs those methods one short unit of work; other methods do not pay for it. `prompts/get`,
  `resources/read`, subscriptions and completions stay live.
- **A member's list-change notification re-discovers it first,** then clients are told, so they list the new
  snapshot.

## Alternatives considered

- **Load the listings into the bundle view.** Every request, `tools/call` included, would read them.
- **Keep `private` listings per forwarded identity, with their `ttlMs`.** That is a second cache keyed by credentials,
  with expiry, for members that are listed live today at no worse cost than before. Left out.
- **Treat the SDK's default `private` as "no scope".** The wire cannot tell a default from an intent, and a server
  that means `private` must not be shared. The operator's `shared` covers servers whose default is wrong.
- **Leave the identity header out of the sharing rule.** The header exists so an upstream on the gateway's network can
  trust who is calling, and it may filter on it. Only the operator knows it does not, hence `shared`.
- **Fill a missing snapshot from a live answer.** A database write on the request path, for a state that discovery
  ends anyway.

## Consequences

### Positive

- A bundle of members whose lists are shareable can be connected to and listed with every member at zero.
- A member that is down still contributes its last listing, as its tools do.

### Trade-offs

- A member whose lists change without a `list_changed` it can deliver, or while upstream pooling is off, is served the
  old listing until its next discovery. The periodic refresh (ADR-0038) and the explicit refresh bound that.
- FastMCP and other MCP Python SDK servers on revision 2026-07-28 mark lists `private` unless their author sets a
  scope, so under `auto` they stay live until the server declares `public` or the operator chooses `shared`.
- A deployment that upgrades has no snapshots until each server's next discovery. Unchanged upserts do not probe
  (ADR-0043), so `:refresh-tools` once, or the periodic refresh, fills them.
