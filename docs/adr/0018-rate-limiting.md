# ADR-0018: Redis fixed-window rate limiting + auth-failure lockout

**Status:** accepted · **Date:** 2026-07-03

## Context

The gateway had **zero abuse protection** (spec 16, EP-16..22): no per-endpoint or per-client traffic limits and no
auth-failure throttling. Only scaffolding existed — the `Endpoint.rate_limit` JSON column, a `RATE_KEY` template, and an
unconsumed `settings.trusted_proxies`. metamcp had rate limiting but with a documented flaw: per-process counters, so
"each machine counts only its own traffic." bundlemcp is multi-replica by design (ARC-9), so any limit has to be shared
state. This ADR records how the limits were implemented.

## Decision drivers

- Fixed-window `INCR`+`EXPIRE` is the simplest correct shared-state limiter and the only one that is both hermetically
  testable (fakeredis) and replica-safe.
- Separating the auth-failure limiter from traffic limits lets it be gateway-wide and IP-keyed with a fixed policy,
  matching metamcp's behavior, without entangling it with per-endpoint config.
- Fail-open keeps a Redis blip from taking the whole gateway down; the opt-in fail-closed covers endpoints that would
  rather shed load than over-serve.

## Decision

- **Algorithm — fixed-window counter** via atomic `INCR` + `EXPIRE`, bucketed by **Redis server time** (`TIME`,
  ARC-15/EP-22): `bucket = now // window`, `INCR bmcp:rate:{scope}:{bucket}`, `EXPIRE window*2` on the first hit,
  `allowed = count <= limit`, `retry_after = window - (now % window)`. Spec 16 explicitly lists `INCR`+`EXPIRE` as
  acceptable (EP-17); it needs no Lua (so it runs under fakeredis in the hermetic suite), it is shared across replicas,
  and it is what metamcp used. Boundary-burst (up to 2× at a window edge) is the known trade-off; a sliding-window-log
  upgrade is a noted follow-up.
- **Two traffic limits per endpoint (EP-16):** an **endpoint** limit (`scope=ep:{name}:all`, all callers) and a
  **per-client** limit (`scope=ep:{name}:{identity}`) where identity is the OAuth user, else the API key id, else the
  client IP (EP-6). Both are validated `RateLimitConfig` / `RateRule` DTOs but still stored as JSON on the endpoint.
  Enforced on `tools/call`; `initialize`/`tools/list` are exempt unless `include_initialize_list` is set (EP-19).
- **Auth-failure lockout (EP-20):** a separate gateway-wide `AuthFailureLimiter` keyed by **client IP**, policy from
  `BUNDLEMCP_AUTH_FAILURE_LIMIT/WINDOW` settings. Applied wherever credentials fail — the MCP edge
  (`POST`/`GET /{endpoint}/mcp`) and the OAuth token endpoint (`invalid_client`/`invalid_grant`). Over the threshold →
  429 + `Retry-After` instead of the usual 401. A valid credential never touches it.
- **Fail-open by default (EP-21):** any Redis error during a check logs WARN, bumps a metric, and **allows** the
  request; an endpoint may opt into `fail_closed` for its traffic limits. The auth-failure limiter always fails open
  (availability over lockout) with its own alarm metric.
- **Client IP (EP-22 / DEP-2 partial):** `gateway/proxy.py::client_ip` honors `X-Forwarded-For` (leftmost) **only**
  when the socket peer is in `settings.trusted_proxies` (CIDR match); otherwise the peer. This satisfies EP-22 and the
  client-IP half of DEP-2 — `X-Forwarded-Proto/Host` stay with spec 71.
- **Metrics (EP-18):** rejections / fail-opens / auth-failures / lockouts are counted in an in-process `Counters`
  holder on the runtime. Metrics are replica-local by nature (each Prometheus target scrapes its own process), so
  in-memory counters are correct. A rejection is a **metric, never an audit record** (audit is tool calls only). The
  Prometheus `/metrics` export is spec 51's job — this milestone increments the counters and structures them for that
  exporter; it does not build `/metrics`.

## Alternatives considered

_Not recorded at the time of the decision._

## Consequences

### Positive

- Public endpoints have real abuse/DoS protection that holds across replicas — metamcp's per-process-counter flaw is
  fixed.
- Credential scanning is slowed per-IP at both auth surfaces.
- The counter seam is ready for the spec-51 `/metrics` exporter.

### Trade-offs

- Boundary bursts up to 2× at window edges (fixed-window trade-off); revisit with a sliding-window log if it matters.
- IP-keyed auth-failure lockout can over-block callers behind a shared NAT; acceptable because it only ever adds a delay
  (fail-open, windowed) and the threshold defaults high (20 / 5 min).

