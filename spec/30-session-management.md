# 30 — Session management

**Status:** Accepted · **Origin:** new (the architectural fix for metamcp's #1 failure mode)
**Prior art (what NOT to do):** `../metamcp/apps/backend/src/lib/metamcp/mcp-server-pool.ts`, `metamcp-server-pool.ts`, `session-lifetime-manager.ts`, `session-error.ts`

## Summary

metamcp bound every MCP session to the memory of the process that created it:
restarts produced `404 Session not found` storms, horizontal scaling was
impossible, and an entire recovery subsystem existed to paper over it.
bundlemcp's rule: **a session is data, not an object** — its state lives in
Redis, any replica can serve it, and restarts are non-events.

## Requirements

### Downstream sessions (client ↔ bundlemcp)

- **SES-1** On `initialize`, create a session record in Redis keyed by the
  issued `Mcp-Session-Id`: endpoint, bundle, resolved caller identity,
  negotiated protocol version/capabilities, timestamps, and a record-schema
  `version` field ([DEP-6](71-deployment.md)). TTL = configurable session
  lifetime, refreshed on activity (a `ping` counts —
  [PROT-8](32-protocol-passthrough.md)).
- **SES-1a** Concurrent updates to one session record (e.g. two requests
  lazily binding different servers, SES-6) MUST be atomic — optimistic
  check-and-set (WATCH/Lua) or a short per-session lock; lost updates are a
  correctness bug, not an accepted race.
- **SES-2** Any replica MUST be able to serve any request carrying a valid
  session id by loading this record — no process-local session registry may
  be required for request handling ([ARC-9](01-architecture.md)).
- **SES-3** Unknown/expired session id → the Streamable-HTTP-prescribed 404,
  prompting the client to re-initialize. This MUST happen only for genuinely
  expired/invalid sessions — never because a different replica answered or
  the gateway restarted ([ARC-10](01-architecture.md)).
- **SES-4** Explicit `DELETE …/mcp` terminates the session and releases its
  upstream bindings.

### Upstream connections (bundlemcp ↔ servers)

- **SES-5** Upstream Streamable HTTP sessions are represented by their
  **session id + endpoint URL + headers** (data in Redis), re-establishable
  from any replica. Live HTTP connections are per-replica transport details;
  losing one MUST NOT lose the upstream session when the upstream is
  spec-compliant.
- **SES-6** Binding model: a downstream session binds lazily (first call per
  server) to one upstream session per member server. Bindings are stored in
  the Redis session record. When identity is forwarded
  ([FWD-5](24-identity-forwarding.md)) or upstream OAuth is `per_user`
  ([UPO-2](23-upstream-oauth.md)), bindings are keyed by caller identity and
  MUST never be shared across identities; identity-free servers MAY share
  pooled upstream sessions for efficiency.
- **SES-7** Upstream failure handling (carrying over the fork's hard-won
  lessons as *first-class* behavior, not recovery hacks): on upstream 404
  ("session not found") or transport loss — re-initialize the upstream
  session, rebind, and retry the in-flight request **once**; on repeated
  failure return a structured error and feed `health_status`
  ([SRV-4](10-server-registry.md)).
- **SES-8** Connection caps: max concurrent upstream sessions global and
  per-server (runtime-configurable). Under pressure, evict least-recently-used
  identity-free pooled sessions first. No pre-warming complexity in v1;
  measure cold-start first, optimize later.
- **SES-9** Config changes to a server invalidate its pooled upstream
  sessions ([SRV-6](10-server-registry.md)) via the invalidation event
  stream ([33-state-propagation.md](33-state-propagation.md)) so all
  replicas drop their transports.

### Cross-replica delivery

- **SES-13** Live streams (a client's GET event stream, an in-flight call's
  response stream) are pinned to the replica holding them; everything else is
  not. Messages that must reach a specific stream from another replica —
  cancellations, list-changed notifications, server→client requests and
  their responses ([32-protocol-passthrough.md](32-protocol-passthrough.md))
  — are routed via Redis pub/sub channels keyed by session id, delivered by
  the replica holding the stream. A message for a session with no live
  stream anywhere fails fast with a structured error (or is dropped, for
  notifications).

### Degradation matrix

- **SES-14** Explicit outage behavior (replaces any "graceful" hand-waving):

  | Failure | Behavior |
  |---|---|
  | **Redis down** | Session-dependent MCP requests → 503 + `Retry-After` (no false 404s); after recovery, records with intact TTLs resume, otherwise clients re-`initialize`. Rate limits per [RATE-6](16-rate-limiting.md). Admin UI logins unavailable; `readyz` false. |
  | **Postgres down** | Existing sessions keep serving from cached config/tool data where possible; token/key validation fails closed (401/503); config mutations and audit writes fail (audit queue buffers per [AUD-3](50-audit-log.md)); `readyz` false. |
  | **Single replica dies** | Its pinned streams drop; clients retry/reconnect and any replica serves them (SES-2); in-flight calls on that replica surface as retryable errors. |

### Lifecycle & shutdown

- **SES-10** A periodic sweeper expires idle sessions (Redis TTL is the
  backstop; the sweeper handles bindings/metrics). Session lifetime is
  runtime-configurable (`Config`), default 24h; `null` disables idle expiry
  (sessions live until explicitly terminated — metamcp parity).
- **SES-11** Graceful shutdown: stop accepting new requests, drain in-flight
  ones (bounded), exit. Session records persist in Redis — clients continue
  on other replicas or after restart without re-initializing.
- **SES-12** Integration tests MUST cover: restart-under-load (session
  survives a gateway restart), two-replica round-robin (alternating requests
  on one session succeed), and upstream-restart recovery (SES-7).

## Out of scope

- Resumability/redelivery of streamed responses across replicas
  (`Last-Event-ID` replay). v1 guarantees session continuity, not
  mid-stream event replay; a lost stream surfaces as a retryable request.
- Sticky-session load-balancer requirements — explicitly rejected; the design
  goal is NO stickiness.

## Open questions

- How much of FastMCP v3's session/transport layer can be used as-is vs.
  where bundlemcp must drop to the low-level SDK to externalize session state
  — the first implementation spike answers this and refines SES-5/6.
