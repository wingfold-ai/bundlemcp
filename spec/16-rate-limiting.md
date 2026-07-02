# 16 — Rate limiting

**Status:** Accepted · **Origin:** improvement (metamcp had per-process counters; bundlemcp is Redis-backed)
**Prior art:** `../metamcp/apps/backend/src/middleware/rate-limit.middleware.ts`, `lib/rate-limit.ts`

## Summary

Optional per-endpoint rate limits enforced in Redis so they hold across all
gateway replicas — fixing metamcp's documented "each machine counts only its
own traffic" limitation.

## Requirements

- **RATE-1** Two independent optional limits per endpoint (`rate_limit` json):
  - **endpoint limit**: max requests per window across all callers;
  - **per-client limit**: max requests per window per caller, keyed by
    resolved identity ([EP-6](14-endpoints.md)) — user `sub` or API key id —
    falling back to client IP for `none`-auth endpoints.
- **RATE-2** Enforcement uses Redis (sliding window or token bucket via
  atomic Lua/`INCR`+`EXPIRE`), shared by all replicas. No in-process counters
  ([ARC-9](01-architecture.md)).
- **RATE-3** Exceeding a limit returns HTTP 429 with `Retry-After`; rejections
  are counted in metrics ([51-observability.md](51-observability.md)) but are
  NOT audit records (audit is tool calls only).
- **RATE-4** Limits apply to MCP `tools/call` requests; `initialize` and
  `tools/list` SHOULD be exempt-by-default to avoid breaking client startup,
  with a per-endpoint flag to include them.
- **RATE-5** Authentication failures are rate-limited separately (fixed
  gateway-wide policy, Redis-backed) to slow credential scanning — carry-over
  of metamcp's auth rate limiter.

## Out of scope

- Billing/credit enforcement (that is the application layer's metering hook —
  [31-middleware.md](31-middleware.md)).
- Global (cross-endpoint) traffic shaping.

## Open questions

- None.
