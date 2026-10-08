# 30 — Session management

**Status:** Accepted · **Origin:** new (the architectural fix for metamcp's #1 failure mode)
**Prior art (what NOT to do):** `../metamcp/apps/backend/src/lib/metamcp/mcp-server-pool.ts`, `metamcp-server-pool.ts`,
`session-lifetime-manager.ts`, `session-error.ts`

## Summary

metamcp bound every MCP session to the memory of the process that created it: restarts produced `404 Session not found`
storms, horizontal scaling was impossible, and an entire recovery subsystem existed to paper over it. bundlemcp's rule:
**a session is data, not an object** — its state lives in Redis, any replica can serve it, and restarts are non-events.

MCP 2026-07-28 removed protocol-level sessions altogether: every request is self-contained. bundlemcp serves both eras
([PROT-13](32-protocol-passthrough.md)): handshake-era clients get the session model below unchanged; modern-era
requests carry everything a session used to hold (SES-15), so for them the any-replica rule is satisfied by
construction. What remains replica-pinned in both eras is a *live stream*, never a session (SES-13).

## Requirements

### Downstream sessions (handshake-era clients ↔ bundlemcp)

SES-1 to SES-4 apply to clients that open with `initialize` (revisions 2025-11-25 and earlier). A modern-era request
never creates, reads or requires a session record.

- **SES-1** On `initialize`, create a session record in Redis keyed by the issued `Mcp-Session-Id`: endpoint, bundle,
  resolved caller identity, negotiated protocol version/capabilities, the client's requested log level
  ([PROT-7](32-protocol-passthrough.md)), timestamps, and a record-schema `version` field ([DEP-6](71-deployment.md)).
  TTL = configurable session lifetime, refreshed on activity (a `ping` counts — [PROT-8](32-protocol-passthrough.md)).
- **SES-1a** Concurrent updates to one session record (e.g. two requests lazily binding different servers, SES-6) MUST
  be atomic — optimistic check-and-set (WATCH/Lua) or a short per-session lock; lost updates are a correctness bug, not
  an accepted race.
- **SES-2** Any replica MUST be able to serve any request carrying a valid session id by loading this record — no
  process-local session registry may be required for request handling ([ARC-9](01-architecture.md)).
- **SES-3** Unknown/expired session id → the Streamable-HTTP-prescribed 404, prompting the client to re-initialize. This
  MUST happen only for genuinely expired/invalid sessions — never because a different replica answered or the gateway
  restarted ([ARC-10](01-architecture.md)).
- **SES-3a** A session belongs to the endpoint and the caller that opened it. A `POST`, `GET` or `DELETE` naming a
  session is admitted like any other request first: an unknown endpoint is 404 and a missing or invalid credential gets
  the 401 challenge, both before the session is looked at. It is then served only when the session was opened on the
  endpoint in the path **and** the authenticated caller has the same identity subject as the one that opened it (the
  same user, else the same API key). Otherwise it is answered exactly like an unknown session (SES-3) — never 403, so a
  session id cannot be probed for existence or used by anyone it leaks to.
- **SES-4** Explicit `DELETE …/mcp` terminates the session and releases its upstream bindings, subject to SES-3a. A
  `DELETE` (or `GET`) without an `Mcp-Session-Id` is answered 405 ([EP-1](14-endpoints.md)).

### Stateless requests (modern-era clients ↔ bundlemcp)

- **SES-15** A request carrying `_meta["io.modelcontextprotocol/protocolVersion"]` is admitted on its own: the caller
  identity is resolved from its credentials, the protocol version, client capabilities and log level are read from
  `_meta`, and a per-request routing key replaces the session id for in-flight bookkeeping (cancellation, progress,
  parked calls). No record is written to Redis and no `Mcp-Session-Id` is minted or echoed; one present on the request
  is ignored. Any replica serves any modern request without lookup ([ARC-9](01-architecture.md)).
- **SES-16** A **parked call** ([PROT-18](32-protocol-passthrough.md) park and resume) is the one modern-era object that
  is replica-pinned: the in-flight upstream call waiting for the client's retry. It is registered on its replica under
  the correlation id sealed into `requestState`, lives at most for the call's remaining PROT-2 budget, and is reached
  from any replica via the SES-13 signal bus. A retry that no replica claims within a short grace period falls back to a
  re-run (PROT-18); a replica that dies loses only the parked calls it held, exactly as it loses its live streams.

### Upstream connections (bundlemcp ↔ servers)

- **SES-5** Upstream Streamable HTTP sessions are represented by their **session id + endpoint URL + headers** (data in
  Redis), re-establishable from any replica. Live HTTP connections are per-replica transport details; losing one MUST
  NOT lose the upstream session when the upstream is spec-compliant.
- **SES-6** Binding model: a downstream session binds lazily (first call per server) to one upstream session per member
  server. Bindings are stored in the Redis session record. When identity is forwarded
  ([FWD-5](24-identity-forwarding.md)) or upstream OAuth is `per_user` ([UPO-2](23-upstream-oauth.md)), bindings are
  keyed by caller identity and MUST never be shared across identities; identity-free servers MAY share pooled upstream
  sessions for efficiency.
- **SES-7** Upstream failure handling (carrying over the fork's hard-won lessons as *first-class* behavior, not recovery
  hacks): on upstream 404 ("session not found") or transport loss — re-initialize the upstream session, rebind, and
  retry the in-flight request **once**; on repeated failure return a structured error and feed `health_status`
  ([SRV-4](10-server-registry.md)).
- **SES-8** Connection caps: max concurrent upstream sessions global and per-server (runtime-configurable). Under
  pressure, evict least-recently-used identity-free pooled sessions first. No pre-warming complexity in v1; measure
  cold-start first, optimize later.
- **SES-9** Config changes to a server invalidate its pooled upstream sessions ([SRV-6](10-server-registry.md)) via the
  invalidation event stream ([33-state-propagation.md](33-state-propagation.md)) so all replicas drop their transports.

### Cross-replica delivery

- **SES-13** Live streams (a handshake client's GET event stream, a modern client's `subscriptions/listen` stream, an
  in-flight call's response stream, a parked call) are pinned to the replica holding them; everything else is not. Each
  stream is registered under a **stream key** — endpoint, bundle and a stream id that is the session id for handshake
  clients and the request id for modern ones — so list-changed fan-out selects streams by endpoint or bundle without
  loading a session. Messages that must reach a specific stream from another replica — cancellations, list-changed
  notifications, server→client requests and their responses, MRTR resumes and results
  ([32-protocol-passthrough.md](32-protocol-passthrough.md)) — are routed via Redis pub/sub channels keyed by stream id
  or correlation id, delivered by the replica holding the target. A message for a target with no live holder anywhere
  fails fast with a structured error (or is dropped, for notifications).

### Degradation matrix

- **SES-14** Explicit outage behavior (replaces any "graceful" hand-waving):

  | Failure | Behavior |
  |---|---|
  | **Redis down** | Session-dependent MCP requests → 503 + `Retry-After` (no false 404s); after recovery, records with intact TTLs resume, otherwise clients re-`initialize`. Rate limits per [RATE-6](16-rate-limiting.md). Admin UI logins unavailable; `readyz` false. |
  | **Postgres down** | Existing sessions keep serving from cached config/tool data where possible; token/key validation fails closed (401/503); config mutations and audit writes fail (audit queue buffers per [AUD-3](50-audit-log.md)); `readyz` false. |
  | **Single replica dies** | Its pinned streams drop; clients retry/reconnect and any replica serves them (SES-2); in-flight calls on that replica surface as retryable errors. |

### Lifecycle & shutdown

- **SES-10** A periodic sweeper expires idle sessions (Redis TTL is the backstop; the sweeper handles bindings/metrics).
  Session lifetime is runtime-configurable (`Config`), default 24h; `null` disables idle expiry (sessions live until
  explicitly terminated — metamcp parity).
- **SES-11** Graceful shutdown: stop accepting new requests, drain in-flight ones (bounded), exit. Session records
  persist in Redis — clients continue on other replicas or after restart without re-initializing.
- **SES-12** Integration tests MUST cover: restart-under-load (session survives a gateway restart), two-replica
  round-robin (alternating requests on one session succeed), and upstream-restart recovery (SES-7).

## Out of scope

- Resumability/redelivery of streamed responses across replicas (`Last-Event-ID` replay). v1 guarantees session
  continuity, not mid-stream event replay; a lost stream surfaces as a retryable request.
- Sticky-session load-balancer requirements — explicitly rejected; the design goal is NO stickiness.

## Open questions

- ~~How much of FastMCP v3's session/transport layer can be used as-is?~~ **Resolved** by the implementation spike: the
  endpoint edge is implemented directly (FastAPI + Redis session records); FastMCP v3 serves the upstream client side
  only. See [ADR-0011](../docs/adr/0011-own-streamable-http-edge.md).
