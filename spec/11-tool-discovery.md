# 11 — Tool discovery & cache

**Status:** Accepted · **Origin:** metamcp carry-over **Prior art:**
`../metamcp/apps/backend/src/lib/metamcp/fetch-metamcp.ts`, `tools-sync-cache.ts`

## Summary

bundlemcp discovers each server's tools via MCP `tools/list` and caches the definitions (name, description, title, input
schema, annotations) in Postgres. The cache lets admins curate bundles even while an upstream is down, and is the
substrate for per-bundle overrides ([13-tool-management.md](13-tool-management.md)).

## Requirements

- **DISC-1** Discovery MUST run on server create/update ([SRV-2](10-server-registry.md)), including a bootstrap upsert
  once its document has committed ([BOOT-7](41-bootstrap.md)), on explicit "refresh tools"
  from UI/API, on the periodic refresh (DISC-7), and after an upstream OAuth connect completes
  ([UPO-9](23-upstream-oauth.md)). An endpoint's `tools/list` is served from the cache (DISC-4) and never reaches an
  upstream, so serving it does not trigger discovery; the periodic refresh covers what that would have caught
  ([ADR-0038](../docs/adr/0038-periodic-tool-refresh.md)). An `upstream_oauth` server is probed with a connected
  account's bearer; until one exists it is reported as not connected, not as failing. A discovery that changes the tool
  set invalidates every bundle containing the server, so live clients re-list ([BND-7](12-bundles.md)).
- **DISC-2** Sync is hash-based: compute a stable hash per tool definition; write to Postgres only when the hash changed
  (metamcp's `tools-sync-cache` behavior) to keep the hot path write-free in the common case.
- **DISC-3** Tools that disappear from the upstream are **not deleted**: they keep their `BundleTool` curation but stop
  being served; `last_seen_at` lets the UI mark them stale. Explicit deletion happens via "refresh & prune" in the
  UI/API.
- **DISC-4** Serving `tools/list` on an endpoint MUST work from the Postgres cache when the upstream is unreachable,
  with the failure surfaced in `health_status` ([SRV-4](10-server-registry.md)) and logged — a degraded response MUST be
  observable, never silent (metamcp's silent-partial-failure hazard).
- **DISC-5** Tool input schemas are stored verbatim (json) and served unmodified unless a profile or override transforms
  them.
- **DISC-6** Discovery also captures the server's **advertised capabilities** from the upstream `initialize` result
  (which of tools/prompts/resources/ completions/logging it supports, plus `listChanged`/`subscribe` flags) into
  `McpServer.capabilities` ([SRV-1](10-server-registry.md), [DOM](02-domain-model.md)). This snapshot is the source for
  capability aggregation ([PROT-11](32-protocol-passthrough.md)) so `initialize` need not fan out to members. Refreshed
  on every discovery run; degrade-observably on failure (DISC-4), keeping the last-known snapshot.
- **DISC-7** Periodic refresh: every `BUNDLEMCP_DISCOVERY_REFRESH_INTERVAL` seconds (default 1800; `0` disables it) the
  gateway re-runs discovery for every registered server, one server at a time. Only one replica refreshes per interval:
  the run takes a shared, self-expiring lease in Valkey, and a replica that finds it held skips that tick. Each run is
  an ordinary discovery, so a changed tool set is announced (BND-7), and failures count toward `health_status` like any
  other probe ([SRV-4](10-server-registry.md)): an upstream that stays unreachable is marked `error` after that many
  refreshes instead of staying `unknown`. One server's failure never stops the run for the rest, and every discovery
  probe is bounded (60 s) so a hanging upstream fails instead of stalling the run. This covers the upstreams the other
  triggers miss: one that was unreachable when it was registered, and one whose tools change while no call is open to
  it. Per-call upstream connections ([ADR-0012](../docs/adr/0012-per-call-upstream-connections.md)) never receive a
  `list_changed` sent between calls ([PROT-10](32-protocol-passthrough.md) residual). Rationale and the alternatives
  weighed: [ADR-0038](../docs/adr/0038-periodic-tool-refresh.md).

## Out of scope

- **Content** discovery of resources/prompts is handled in [12-bundles.md](12-bundles.md) (live pass-through, not cached
  in v1) — only the capability *flags* above are stored, never the prompt/resource lists themselves.

## Open questions

- ~~Whether `tools/list_changed` notifications from upstreams should trigger re-discovery in v1 or be deferred.~~
  **Resolved:** required by [PROT-10](32-protocol-passthrough.md), with downstream propagation per
  [BND-7](12-bundles.md). Per-call upstream connections cannot receive a `list_changed` sent between calls (PROT-10
  residual), and the gateway does not yet re-discover on one received during a call; the periodic refresh (DISC-7)
  bounds how stale the cache gets meanwhile.
