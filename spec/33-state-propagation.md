# 33 — Configuration state propagation

**Status:** Accepted · **Origin:** new (generalizes SES-9; fixes the KEY-4/KEY-5 contradiction)

## Summary

Replicas may cache configuration (endpoint lookups, bundle composition, API key validity, runtime `Config`) for hot-path
speed — but every cache MUST be invalidated by explicit events, not TTL expiry alone. One mechanism, all config classes:
write to Postgres, publish an invalidation event on Redis pub/sub, every replica drops/refreshes its cached entry.

## Requirements

- **STP-1** Every mutation of configuration state — `McpServer`, bundle membership, `BundleTool` curation, `Endpoint`,
  `ApiKey`, runtime `Config` keys — MUST publish an invalidation event (`{entity_type, id/natural_key, action}`) on a
  well-known Redis pub/sub channel after the Postgres commit.
- **STP-2** Replicas subscribe from startup; on event receipt they MUST invalidate the affected local cache entries. On
  (re)connect to Redis after a gap, a replica MUST flush all config caches (it may have missed events).
- **STP-3** Propagation budget: a config change MUST be effective on all replicas within **2 seconds** under normal
  operation. Integration tests assert this for at least: endpoint disable ([EP-5](14-endpoints.md)), API key
  deactivation ([KEY-4](22-api-keys.md)), tool disable ([TM-2](13-tool-management.md)).
- **STP-4** API-key semantics reconciled: [KEY-5](22-api-keys.md)'s Redis/local validation cache is permitted **only**
  in combination with STP-1 invalidation on deactivate/delete — "immediately" in KEY-4 means within the STP-3 budget,
  never "when a TTL happens to expire".
- **STP-5** Server-config invalidation additionally tears down pooled upstream transports
  ([SES-9](30-session-management.md)) — that behavior rides the same event stream.
- **STP-6** Caching is an optimization, never a correctness dependency: with caching disabled entirely (config flag for
  debugging), behavior MUST be identical, only slower.

## Out of scope

- Cache coherence for *data* state (tool cache freshness is spec 11's concern; sessions are spec 30's).

## Open questions

- None.
