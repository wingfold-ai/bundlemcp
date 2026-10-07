# 16 — Rate limiting

**Status:** Accepted · **Origin:** improvement (metamcp had per-process counters; bundlemcp is Redis-backed)
**Prior art:** `../metamcp/apps/backend/src/middleware/rate-limit.middleware.ts`, `lib/rate-limit.ts`

## Summary

Optional per-endpoint rate limits enforced in Redis so they hold across all gateway replicas — fixing metamcp's
documented "each machine counts only its own traffic" limitation.

## Requirements

- **RATE-1** Two independent optional limits per endpoint (`rate_limit` json):
  - **endpoint limit**: max requests per window across all callers;
  - **per-client limit**: max requests per window per caller, keyed by resolved identity ([EP-6](14-endpoints.md)) —
    user `sub` or API key id — falling back to client IP for `none`-auth endpoints.
- **RATE-2** Enforcement uses Redis (sliding window or token bucket via atomic Lua/`INCR`+`EXPIRE`), shared by all
  replicas. No in-process counters ([ARC-9](01-architecture.md)).
- **RATE-3** Exceeding a limit returns HTTP 429 with `Retry-After`; rejections are counted in metrics
  ([51-observability.md](51-observability.md)) but are NOT audit records (audit is tool calls only).
- **RATE-4** Limits apply to MCP `tools/call` requests; `initialize` and `tools/list` SHOULD be exempt-by-default to
  avoid breaking client startup, with a per-endpoint flag to include them.
- **RATE-5** Authentication failures are rate-limited separately (fixed gateway-wide policy, Redis-backed) to slow
  credential scanning — carry-over of metamcp's auth rate limiter. A locked-out client's standing is checked **before**
  its credential is evaluated, so a lockout refuses correct credentials too rather than only shaping the error it gets.
- **RATE-6 Redis-outage stance:** traffic limits (RATE-1) **fail open** with a loud metric + WARN log (an endpoint may
  opt into fail-closed via its `rate_limit` config); the auth-failure limiter (RATE-5) also fails open but raises a
  dedicated alarm metric — availability over throttling, never silently.
- **RATE-7** Client IP for the `none`-auth fallback derives from the trusted-proxy policy ([DEP-2](71-deployment.md));
  windows use Redis server time ([ARC-15](01-architecture.md)).

## Out of scope

- Billing/credit enforcement (that is the application layer's metering hook —
  [31-middleware.md](31-middleware.md)).
- Global (cross-endpoint) traffic shaping.

## Implementation

**Implemented** ([ADR-0018](../docs/adr/0018-rate-limiting.md)). The chosen RATE-2 algorithm is the
**fixed-window counter** (`INCR`+`EXPIRE`, bucketed by Redis `TIME`) — `infrastructure/valkey/rate_limiter.py`
`ValkeyRateLimiter`. Enforcement lives in `api/mcp/rate_limit_gate.py`: the endpoint + per-client checks gate
`tools/call` (RATE-1/3/4/6/7), and the gateway-wide `AuthFailureLimiter` (RATE-5) gates the MCP edge and the OAuth token
endpoint. Client IP derives from `api/http/client_ip.py::client_ip` (RATE-7 / DEP-2 client-IP half). Rejections and
lockouts increment in-process counters (`infrastructure/inprocess/counters.py`); the RATE-3 Prometheus `/metrics` export
is deferred to
[51-observability.md](51-observability.md).

## Open questions

- None.
