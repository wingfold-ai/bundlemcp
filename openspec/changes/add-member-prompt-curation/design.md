# Design

## Context

See [proposal.md](proposal.md) — this is an optional feature behind a go/no-go. Today `DiscoveryService`
(application) probes `tools/list` through `UpstreamProbe` and snapshots capabilities (UPS-22); member prompts and
resources are fetched live per request by `MemberFanout` (`api/mcp/dispatch/handlers/member_fanout.py`), whose
`merged(...)` takes a `present` callback per entry. `BundleView` (domain) is composed once per request and already
carries the bundle's own prompts and resources (BND-25).

## Goals / Non-Goals

**Goals:**

- Curation of member prompts and resources with the same feel as tool curation: enable flag plus title and description
  overrides, per bundle.
- Serving stays live passthrough; the cache is for the admin UI only, so nothing a client sees depends on its
  freshness except which entries are curated.

**Non-Goals:**

- Renaming member prompts (the prefixed name is the routing key) or changing resource URIs.
- Curating resource templates, completions or subscriptions.
- Serving from the cache when a member is down.

## Decisions

### Cache listings at discovery, not on page view

`UpstreamProbe` gains optional `list_prompts` / `list_resources` steps run in the same connection as `tools/list`
when the negotiated capabilities advertise them. New domain entities `MemberPrompt` (server, name, title,
description, hash, stale marker) and `MemberResource` (server, uri, name, title, description, hash, stale marker) in
`domain/servers/`, synced by a sibling of `sync_tools` with the same hash-gating and staleness rules
([complete-tool-curation](../complete-tool-curation/design.md)). The bound is 500 entries per server and kind,
following list pagination up to it; truncation logs `discovery.listing_truncated`.

*Alternative:* the admin UI fetches the member's live listing through a management action when the curation card
opens. Rejected: it contacts the upstream on every page view (ADR-0043), fails while the upstream is down, and leaves
curation records with nothing to show next to them.

### Curation is keyed by the upstream's own identifier

`BundleMemberPrompt` (bundle, member prompt id, enabled, override title, override description) and
`BundleMemberResource` (same shape) in `domain/bundles/`, with row classes, repositories and fakes. The serving path
needs to match a live entry to its curation without the cache, so `BundleView` gains two maps loaded with the
view: `(server name, prompt name) → curation` and `(server name, uri) → curation`, joined through the cached entry in
the loader query. An empty map costs one indexed query per request; a bundle without such curation loads nothing
further.

### The fan-out applies curation through its existing callback

`PromptsListHandler` and `ResourcesListHandler` (api) pass a `present` callback that returns `None` for a disabled
entry and applies title/description overrides; `MemberFanout.merged` drops `None`. `PromptsGetHandler` and
`ResourcesReadHandler` check the view's curation before contacting a member and answer the existing not-found errors.
Resource de-duplication by URI (BND-8) runs before curation, so disabling the winning member's entry does not expose
another member's entry with the same URI.

### Management routes mirror tool curation

`application/management/bundle_service.py` (or a new `MemberContentCurationService` if it grows too large) lists
cached entries of the bundle's members with their curation and writes curation, invalidating the bundle (BND-7:
`notifications/prompts/list_changed` / `resources/list_changed` on open streams, as BND-28 does for bundle-owned
entries). DTOs in `application/schemas/bundles/`, one per file, every field described. Controllers in
`api/management/controllers/`.

## Risks / Trade-offs

- [Per-user upstreams (`upstream_oauth`, per-user tokens) list different prompts per user] → Discovery lists with the
  connected account it already uses (UPS-17); entries only some users see are curatable but may be absent for others.
  Documented as a limit.
- [A member whose listing changes every probe (dynamic resources)] → Hash-gating limits writes; the bound limits size;
  curation keyed by URI survives the churn.
- [Extra upstream requests per probe] → Only for members advertising the capability, and only on probes that already
  happen (create, update, refresh, UPS-23).

## Migration Plan

One Alembic revision creating four tables; no backfill — the cache fills on the next probe of each server (at most one
UPS-23 interval), and curation starts empty. Rollback drops the tables; serving is unaffected because it never read
them without curation present.
