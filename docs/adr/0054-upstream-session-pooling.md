# ADR-0054: Upstream sessions are pooled per replica and continued from the session record

**Status:** accepted · **Date:** 2026-10-16 · **Amends:** [ADR-0012](0012-per-call-upstream-connections.md),
[ADR-0021](0021-mcp-surface-completion.md)

## Context

ADR-0012 opened a fresh upstream connection, and with it an `initialize`, for every request, and deferred pooling until
cold start had been measured. That kept the gateway simple, but it left three things unbuildable: a member's list
changes and resource updates between calls (nothing is connected to hear them), a handshake session's binding to one
upstream session (it was recorded and never read), and a client's `logging/setLevel` reaching the members. Every call
also paid an upstream handshake. ADR-0021 relayed logging per call and answered `resources/subscribe` without
delivering updates for the same reason.

The spike against FastMCP 4.0.11 and MCP SDK 2.3.0 settled the two points the design depended on. A client whose HTTP
auth flow adds a stored `Mcp-Session-Id` and `MCP-Protocol-Version` continues an upstream session without
`initialize`. A client callback is not told which client request a server→client request relates to.

## Decision drivers

- Never let one caller's credentials or upstream session state serve another caller.
- Any replica serves any request: losing a replica costs at most an upstream re-initialize.
- A standing upstream channel for list changes, log messages and resource updates.
- No pre-warming, health timers or generation counters, the parts of metamcp's pool ADR-0012 rejected.

## Decision

- **A per-replica pool behind a contract.** `UpstreamSessionPool` hands out a lease on one upstream session for one
  request; `PooledUpstreamSessions` keeps live FastMCP clients and builds them through the existing client factory, so
  the egress guard and the response observer stay in one place. Tool calls and the member fan-out lease from it;
  discovery and the probe keep their own connection. `BUNDLEMCP_UPSTREAM_POOLING_ENABLED=false` swaps in a pool that
  opens and closes a connection per lease, which is ADR-0012's behaviour.
- **The key separates identities and configurations.** A pooled session is keyed by the server, a fingerprint of its
  URL, static headers, auth mode and protocol mode, an identity key, and the set of relay handlers it was opened
  with. The identity key is `shared` for a server that forwards no headers, sends no identity header and uses neither
  per-user OAuth nor delegated tokens; otherwise a SHA-256 over the caller's subject, the forwarded headers and, for
  delegated tokens, the endpoint. A session opened under an older configuration never matches a later request.
- **Credentials that change per request are injected.** The upstream OAuth bearer and the delegated token are added
  by an HTTP auth flow that reads them from the current lease, so a session outlives a token refresh and a delegated
  token is still minted per request. Header values are never stored; only hashes are.
- **Leases are exclusive.** With no related request id, a server→client request cannot be routed among concurrent
  requests on one transport, so each transport serves one request at a time; a concurrent request opens another,
  within the caps.
- **A handshake session's binding is dedicated and is the directory.** Its first call to a member opens an upstream
  session for that downstream session alone and records the upstream session id, negotiated version, fingerprint and
  identity key in the session record. Any replica continues it by opening a transport that carries the stored id,
  without `initialize`. A binding whose fingerprint or identity key no longer matches is re-established. Requests
  without a session lease pooled sessions, shared between callers only under the `shared` key.
- **Transports never end an upstream session on close.** Ending one is explicit: a shared session evicted or idle
  past `upstream_session_idle_timeout` is ended with `DELETE`, and a binding's sessions when the client's `DELETE …/mcp`
  ends its session. Losing a transport keeps the upstream session.
- **One retry, and only when it cannot run a tool twice.** `UpstreamRetryPolicy` allows one retry after a 404 for the
  upstream session or a connection that failed before the request was sent, and, for read-only methods, after any
  transport loss. The call re-initializes, rebinds and retries under the same metering idempotency key.
- **Caps are per replica.** `upstream_sessions_max` and `upstream_sessions_per_server_max` are runtime config read on
  every checkout. At a cap the least recently used idle session is evicted, `shared` ones first; with nothing
  evictable the request gets a connection of its own, closed after it.
- **Between-call messages go to an application router.** A session to a handshake upstream that this replica initialized
  keeps the SDK's GET stream; a session to a modern upstream holds a `subscriptions/listen` open for the list changes
  the server advertised and the resources subscribed on it. `UpstreamNotificationRouter` re-discovers a server on
  `tools/list_changed` behind a Valkey gate (`bmcp:rediscover:{server}`, `SET NX EX`), so several replicas hearing one
  change discover once; announces member prompt and resource list changes to the bundles' streams; delivers
  `notifications/resources/updated` to the streams in a Valkey subscription index; and delivers a bound session's log
  messages to its GET stream.
- **Config changes close transports everywhere.** A `server` invalidation event closes that server's transports on
  every replica, idle ones at once and leased ones at release; a resubscribe after a gap closes them all.

## Alternatives considered

- **Keep per-call connections.** Leaves list changes, resource updates and setLevel undeliverable.
- **Multiplex concurrent requests on one session.** Needs the related request id the SDK does not expose.
- **Share identity-free sessions with handshake bindings.** Fewer upstream sessions, but an upstream's per-session
  state (log level, subscriptions) would cross callers.
- **A cluster-wide connection count in Valkey.** A round-trip on every checkout to cap something that is per replica
  anyway.
- **A connection-broker process.** A second deployable to run a cache.

## Consequences

### Positive

- A handshake session's calls after the first send no `initialize`, on any replica.
- Member list changes, resource updates and between-call log messages reach clients.
- An upstream restart costs the client nothing visible.

### Trade-offs

- Each pooled session holds a connection and, when this replica initialized it, a GET stream open upstream.
- A session continued on another replica has no GET stream there; its between-call messages arrive only while the
  replica that initialized it still holds the transport.
- A per-user OAuth session is keyed by the caller's subject, not the token set, since the gateway holds one token set
  per user and server.
- Retrying a read after a transport loss can serve it twice upstream; reads are side-effect free by MCP's contract.
