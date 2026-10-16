# Design: upstream session pooling

## Context

See proposal.md for the motivation. Today:

- `UpstreamCall._call` (`api/mcp/tool_call/upstream_call.py`) and `MemberFanout` build a FastMCP `Client` per request
  through the `UpstreamClientFactory` contract (`infrastructure/fastmcp/client_factory.py`), enter it (connect +
  `initialize`), make one request and close it. The relay handlers (elicitation, sampling, roots, log) are bound at
  construction, per call, from the downstream client's capabilities.
- `UpstreamCall` writes `UpstreamBinding(server_name, identity_key=sub)` into the session record; nothing reads it.
- `server` invalidation events are published (`infrastructure/valkey/publish_invalidation.py`) and the
  `InvalidationSubscriber` fans them out, but only the runtime-config cache listens.
- `ResourcesSubscribeHandler` answers `{}` and logs `resources.subscribe_push_pooling_dependent`.
- Constraint: no in-memory-only state a request depends on (ARC-9); header values are secrets (spec 51, ARC-18) and are
  never stored or logged; the edge's handlers never know which era they serve.

## Goals / Non-Goals

**Goals:**

- Reuse upstream sessions across calls without ever crossing identities.
- Give the gateway a standing upstream channel for list changes, log messages and resource updates.
- Keep every request servable by any replica: losing a replica costs at most an upstream re-initialize.

**Non-Goals:**

- Pre-warming, health timers or generation counters (metamcp's pool; SES-8 forbids pre-warming).
- Cluster-wide connection accounting (caps are per replica — see the proposal's Open decision).
- Replaying upstream notifications missed while no transport was open (as for downstream streams, no `Last-Event-ID`
  replay).

## Decisions

### D1. The pool is a per-replica transport cache behind the existing factory seam

A new contract `UpstreamSessionPool` (`application/contracts/upstream/upstream_session_pool.py`) hands out a **lease**
on an upstream session for one request: `async with pool.lease(server, key, headers, binding, handlers) as session`.
The adapter `PooledUpstreamSessions` (`infrastructure/fastmcp/pooled_upstream_sessions.py`) keeps live FastMCP clients
keyed by `UpstreamSessionKey` and builds them through the existing `default_client_factory`, so egress checks (SEC-1)
and the response observer (UPS-12) stay in one place. `UpstreamCall`, `MemberFanout` and the subscribe and listen
handlers ask the pool instead of the factory; discovery keeps using the factory directly.

*Alternatives:* keep per-call connections (status quo, ADR-0012) — leaves PROT-10/PROT-23 unbuildable; a separate
connection-broker process — a second deployable for a cache.

### D2. The pool key separates identities and configurations

`UpstreamSessionKey` (domain, `domain/sessions/upstream_session_key.py`) = server name + a **config fingerprint** (hash
of URL, static headers, auth mode, protocol mode) + an **identity key**:

| Server kind | Identity key |
|---|---|
| Identity-free (no forwarded headers, no per-user OAuth, no delegated token) | `shared` |
| Forwards caller headers (AUTH-27) | SHA-256 over `sub` and the sorted forwarded header names and values (AUTH-31) |
| `per_user` upstream OAuth (UPS-26) | `sub` + the upstream token set's id — not the access token, which rotates on refresh |
| `delegated_token` (AUTH-32) | `sub` + endpoint — the token itself is minted per request (D3) |

`McpServer.is_identity_free` is a domain property beside `requires_per_user_token`. Because the config fingerprint is
part of the key, a session opened under an older configuration never matches a new request even before the SES-9 event
arrives; the event only frees the transports sooner.

### D3. Per-request headers are injected, not baked into the transport

The transport is constructed with the server's static headers only; the caller-specific headers of each request
(forwarded headers, a refreshed upstream bearer, a fresh delegated token) are added by an `httpx.Auth` flow that reads
them from the lease (`infrastructure/fastmcp/lease_headers.py`), alongside the existing `ResponseObserver`. A pooled
identity-bound session can therefore outlive a token refresh, and a delegated token is still minted per request.

### D4. Bindings are dedicated; sharing is for unbound requests only

A handshake session's binding names an upstream session that serves **only** that downstream session (SES-6): an
upstream that keeps per-session state would otherwise leak it between callers even on an identity-free server. Log level
(PROT-7) and resource subscriptions (PROT-23) are upstream-session state, so they need this anyway. Requests without a
binding — modern-era requests and the read-only fan-out — lease pooled sessions, shared under the `shared` identity key.
A modern client's `resourceSubscriptions` gets a dedicated upstream session per listen stream and member, closed with
the stream.

*Alternative:* share identity-free sessions with handshake bindings too — fewer upstream sessions, but upstream state
crosses callers.

### D5. Concurrent requests multiplex; relay is routed per upstream request

MCP allows concurrent requests on one session, so a lease is not exclusive. Server→client requests and notifications
that arrive on a request's response stream are routed to that request's relay (`ClientRelay`) by the upstream request
id they relate to; messages on the session's standalone stream go to the session-level sink (D6). The first task spikes
whether the MCP SDK exposes the related request id to client callbacks. If it does not, leases for requests that carry
relay handlers become exclusive (the pool opens another session for a concurrent one, within the caps) — the observable
behaviour is the same.

### D6. Between-call messages go through an application-layer router

Each pooled session keeps its standalone stream open: the GET stream for a handshake upstream, a `subscriptions/listen`
request for a modern upstream that advertised list changes or holds resource subscriptions. Messages on it go to
`UpstreamNotificationRouter` (`application/serving/upstream_notification_router.py`, contracts only):

- `*/list_changed` → take a short Valkey gate `bmcp:rediscover:{server}:{list}` (`SET NX EX`), so N replicas re-discover
  once (PROT-10); tool changes then flow through discovery's existing bundle invalidation (BND-7), while prompt/resource
  list changes are signalled straight to the bundles' streams.
- `notifications/resources/updated` → look the URI up in the resource-subscription index
  (`application/contracts/live_state/resource_subscriptions.py`, Valkey adapter
  `infrastructure/valkey/resource_subscription_index.py`, keys `bmcp:rsub:{server}:{uri}` → stream ids) and
  `SignalBus.deliver` to each subscribed stream, on whichever replica holds it.
- `notifications/message` on a bound session → `SignalBus.deliver` to that downstream session's GET stream, filtered by
  its log level; on a shared session it has no owner and is dropped with a debug log.

### D7. Upstream sessions as data: the binding is the directory

The binding in the downstream session record carries what a replica needs to continue an upstream session: upstream
session id, negotiated protocol version, config fingerprint and identity key (SES-5). Shared pooled sessions are not
recorded: nothing depends on reusing a particular one, so losing one costs an `initialize` the client never sees. To
continue a bound session on another replica the adapter opens a transport carrying the stored `Mcp-Session-Id` and
protocol version **without** sending `initialize`. The spike checks the SDK supports this; if not, the adapter supplies
the transport's session id and the client's initialize result from the binding and the server's capability snapshot
(UPS-22).

New `UpstreamBinding` fields are optional with defaults and the record has no `extra="forbid"`, so the schema version
stays 2 and both builds read each other's records during a rollout (DEP-6).

### D8. Failure handling is a domain policy, executed by the call

The adapter classifies failures as `session_expired` (HTTP 404 naming the session), `not_sent` (connect or write
failed) or `lost_after_send`. `UpstreamRetryPolicy` (`domain/sessions/upstream_retry_policy.py`) decides whether one
retry is allowed from the classification and whether the method is read-only (SES-7); `UpstreamCall` and
`MemberFanout` run it: re-initialize through the pool, rebind via `SessionStore.set_binding` (SES-1a), re-subscribe the
binding's resource subscriptions, retry under the same idempotency key. Final failures go to the server's health
counter (UPS-4).

### D9. Invalidation and caps

`main/` registers `pool.invalidate(server_name)` on `server` events and `pool.invalidate_all()` on the subscriber's
reconnect flush (SES-21). Idle transports close at once; leased ones are marked and closed at release. Caps and the idle
timeout are runtime config keys (`upstream_sessions_max`, `upstream_sessions_per_server_max`,
`upstream_session_idle_timeout`, registered in `domain/config/config_registry.py`), read on every checkout so a change
applies through the existing config invalidation. Eviction is LRU over idle sessions, `shared` keys first (SES-8). A
shared session that is evicted or idles out is ended upstream with `DELETE`; a bound one only loses its transport, and
its upstream session is ended when the downstream session ends (SES-4).

### Layer summary

| Piece | Layer |
|---|---|
| `UpstreamSessionKey`, `UpstreamRetryPolicy`, `McpServer.is_identity_free`, new `UpstreamBinding` fields | `domain/` |
| `UpstreamSessionPool`, `ResourceSubscriptions` contracts; `UpstreamNotificationRouter` | `application/` |
| `PooledUpstreamSessions`, lease-header auth flow | `infrastructure/fastmcp/` |
| Resource-subscription index, re-discovery gate | `infrastructure/valkey/` |
| `UpstreamCall`, `MemberFanout`, setLevel / subscribe / unsubscribe / listen handlers | `api/mcp/` |
| Pool construction, invalidation wiring, shutdown close | `main/` |

### Spike results (task 1.1)

Against FastMCP 4.0.11 and MCP SDK 2.3.0, with a FastMCP server served over HTTP:

- **Resuming without `initialize` works.** A client built with `auto_initialize=False`, whose `httpx` auth flow adds
  the stored `Mcp-Session-Id` and `MCP-Protocol-Version` to every request, continues the upstream session: a tool call
  on it succeeds and the upstream sees no second `initialize`. D7 needs no fallback; the lease-header auth flow of D3
  carries the session headers too.
- **The related request id is not exposed.** A client callback receives a `ClientRequestContext` with the
  server→client request's own id and `meta` `None`; nothing names the client request it relates to. D5's fallback
  applies: a lease is exclusive, and a concurrent request on the same key is served on another transport — for a
  bound session, another transport resuming the same upstream session id — within the caps.
- **The stateless revision has no sessions.** A client in `auto` mode against a 2026-07-28 upstream never sends
  `initialize` and gets no session id; pooling such an upstream reuses connections only, and its bindings carry no
  upstream session id.

## Risks / Trade-offs

- [The SDK cannot resume a session without `initialize`, or does not expose the related request id] → spike first (task
  1.1); the fallbacks in D5 and D7 keep the observable behaviour.
- [An upstream that is not spec-compliant forgets sessions silently instead of answering 404] → those calls fail and
  retry once like a 404; persistent misbehaviour shows in health status (UPS-4).
- [A pooled transport holds an open GET stream per upstream session: file descriptors and upstream load] → per-replica
  caps, idle timeout, standalone streams only on sessions that need them (bound, or with subscribers).
- [Retrying a read after transport loss may be served twice upstream] → reads are side-effect free by MCP's contract;
  `tools/call` is retried only when it provably did not run.
- [Rolling deploy mixes pooling and per-call replicas] → bindings stay compatible; a per-call replica ignores the stored
  upstream session id and opens its own, which is the behaviour of today.

## Migration Plan

1. Ship with `BUNDLEMCP_UPSTREAM_POOLING_ENABLED=true`; the flag off restores per-call connections, so rollback is a
   config change, not a redeploy of the previous image.
2. No database migration. Session records keep version 2.
3. Retire the flag one release later once the integration suite (upstream-restart recovery, SES-12) has run green
   against it.

## Open Questions

- Default values for the caps and idle timeout; set from the OPS-13 measurement once the integration suite reports it.
