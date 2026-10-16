# ADR-0056: Members' prompts and resources are cached at discovery, for curation only

**Status:** accepted · **Date:** 2026-10-16 · **Amends:** [ADR-0021](0021-mcp-surface-completion.md) ·
**Amended by:** [ADR-0059](0059-member-lists-served-from-the-discovery-snapshot.md)

## Context

ADR-0021 made members' prompts and resources live, uncurated passthrough with no cache. The only way to hide one
member prompt from one bundle was to disable the whole membership, which also hid every tool of that member. Tools
are curated per bundle because discovery caches them; prompts and resources had nothing to curate against.

## Decision drivers

- Curation of prompts and resources that feels like tool curation: an enable flag and title and description overrides.
- What a client is served stays live from the member; a cache must not go stale in front of a client.
- No extra upstream traffic outside the probes that already happen (ADR-0043).

## Decision

- **Discovery caches the listings.** When a probe's capabilities advertise prompts or resources, the same connection
  lists them and caches, per entry, the prompt name or resource URI with its title and description — never messages
  or content — hash-gated and kept stale when they vanish, as tools are. Up to 500 entries per server and kind; a
  longer listing is cut and logged. A listing that fails leaves the cache as it was.
- **One entity for both kinds.** A `MemberEntry` with a kind (`prompt` or `resource`) and a key (name or URI), and a
  per-bundle `MemberEntryCuration` keyed by the entry: two tables rather than four.
- **The cache feeds curation only.** Served lists are still fetched live; the bundle view carries just the
  bundle's curation, keyed by kind, member and name or URI, so a request matches a live entry without reading the
  cache. A disabled entry is left out of lists and refused on get or read without contacting the member; overrides
  replace only title and description. Resources are de-duplicated by URI before curation, so hiding the first
  member's entry does not expose another member's entry with the same URI.
- **Curation changes announce list changes** to the bundle's streams, as the bundle's own prompts and resources do.

## Alternatives considered

- **List the member live when the curation card opens.** Contacts the upstream on every page view and fails while it
  is down, leaving curation with nothing to show beside it.
- **Serve from the cache.** Makes a client's view depend on discovery freshness.
- **Separate prompt and resource tables.** The same shape twice.

## Consequences

### Positive

- Bundles shape members' prompts and resources the way they shape tools.

### Trade-offs

- A probe of a member that advertises prompts or resources makes one or two more requests.
- An upstream with per-user accounts is listed with the account discovery uses, so an entry only some users see may
  be missing from curation.
- Export, import and bootstrap do not carry this curation yet.
