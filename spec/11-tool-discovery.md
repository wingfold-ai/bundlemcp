# 11 — Tool discovery & cache

**Status:** Accepted · **Origin:** metamcp carry-over
**Prior art:** `../metamcp/apps/backend/src/lib/metamcp/fetch-metamcp.ts`, `tools-sync-cache.ts`

## Summary

bundlemcp discovers each server's tools via MCP `tools/list` and caches the
definitions (name, description, title, input schema, annotations) in Postgres.
The cache lets admins curate bundles even while an upstream is down, and is
the substrate for per-bundle overrides ([13-tool-management.md](13-tool-management.md)).

## Requirements

- **DISC-1** Discovery MUST run on server create/update ([SRV-2](10-server-registry.md)),
  on explicit "refresh tools" from UI/API, and opportunistically whenever the
  gateway performs a live `tools/list` against the upstream while serving an
  endpoint.
- **DISC-2** Sync is hash-based: compute a stable hash per tool definition;
  write to Postgres only when the hash changed (metamcp's `tools-sync-cache`
  behavior) to keep the hot path write-free in the common case.
- **DISC-3** Tools that disappear from the upstream are **not deleted**:
  they keep their `BundleTool` curation but stop being served; `last_seen_at`
  lets the UI mark them stale. Explicit deletion happens via "refresh &
  prune" in the UI/API.
- **DISC-4** Serving `tools/list` on an endpoint MUST work from the Postgres
  cache when the upstream is unreachable, with the failure surfaced in
  `health_status` ([SRV-4](10-server-registry.md)) and logged — a degraded
  response MUST be observable, never silent (metamcp's silent-partial-failure
  hazard).
- **DISC-5** Tool input schemas are stored verbatim (json) and served
  unmodified unless a profile or override transforms them.

## Out of scope

- Discovery of resources/prompts is handled in [12-bundles.md](12-bundles.md)
  (pass-through, not cached in v1).

## Open questions

- Whether `tools/list_changed` notifications from upstreams should trigger
  re-discovery in v1 or be deferred.
