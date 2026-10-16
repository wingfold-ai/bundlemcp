# sessions Specification

## Purpose

Live state that any replica can serve, and keeping every replica's view current. Handshake-era MCP sessions are records
in the RESP store, so any replica serves them and a restart loses nothing; modern-era requests are stateless. Live
streams are pinned to the replica holding them, and messages reach them from any replica over pub/sub. The degradation
matrix says what happens when the RESP store or Postgres is down. Configuration changes publish invalidation events, so
caches on every replica are flushed within a two-second budget.

The MCP messages carried over a session are the protocol slice.

It merges what were separate specs until 2026-10-13: Session management, State propagation.

## Requirements

### Requirement: SES-1 Session record on initialize
SES-1 to SES-4 apply to clients that open with `initialize` (revisions 2025-11-25 and earlier). A modern-era request
SHALL never create, read or require a session record.

On `initialize`, the gateway SHALL create a session record in the RESP store keyed by the issued `Mcp-Session-Id`
(`bmcp:session:{id}`): endpoint, bundle, resolved caller identity, negotiated protocol version, the client's advertised
capabilities, the client's requested log level ([PROT-7](../protocol/spec.md)), the time the
session was created and the time of its last activity, and a record-schema `version` field
([DEP-6](../deployment/spec.md)). The session lives for the idle session lifetime, the runtime-configurable
`session_lifetime` (SES-10), counted from its last activity, which every request on the session refreshes (a `ping`
counts — [PROT-8](../protocol/spec.md)). The record's TTL in the store is that lifetime plus a margin of two sweeper
intervals, so the sweeper normally expires the session first and the TTL is the backstop.

#### Scenario: Initialize writes a record and returns its id
- **WHEN** a handshake-era client sends `initialize` to `/main/mcp` with an API key
- **THEN** the response carries an `Mcp-Session-Id` header
- **AND** a record under `bmcp:session:{id}` holds endpoint `main`, its bundle, the caller identity, the negotiated
  protocol version and equal creation and last-activity times

#### Scenario: Activity refreshes the TTL
- **WHEN** a client sends `ping` on an existing session
- **THEN** the record's TTL is reset to the session lifetime plus the sweeper's margin and its last-activity time is
  the time of the `ping`

#### Scenario: Lifetime follows the runtime setting
- **WHEN** an operator sets `session_lifetime` to 3600 and a client then initializes
- **THEN** the session expires 3600 seconds after its last activity, and the new record's TTL is 3600 seconds plus
  the sweeper's margin

#### Scenario: A record of another schema version is treated as expired
- **WHEN** a stored record's `version` is not one this build reads
- **THEN** loading it deletes it and the request is answered like an unknown session

### Requirement: SES-1a Atomic session record updates
Concurrent updates to one session record (e.g. two requests lazily binding different servers, SES-6) MUST be atomic —
optimistic check-and-set (WATCH/Lua) or a short per-session lock; lost updates are a correctness bug, not an accepted
race.

#### Scenario: Two racing bindings both land
- **WHEN** two requests on one session record bindings for two different servers concurrently
- **THEN** the stored record afterwards holds both bindings

### Requirement: SES-2 Any replica serves any session
Any replica MUST be able to serve any request carrying a valid session id by loading this record — no process-local
session registry may be required for request handling ([ARC-9](../architecture/spec.md)).

#### Scenario: A second client connection reuses the session
- **WHEN** a session is opened through one HTTP client and a `ping` naming it arrives through another
- **THEN** the `ping` is answered `200` with an empty result

#### Scenario: Session survives a gateway restart
- **WHEN** a session is opened and the gateway process is restarted
- **THEN** a `tools/list` on the same session id succeeds without a new `initialize`

### Requirement: SES-3 Unknown sessions answer 404
Unknown/expired session id → the Streamable-HTTP-prescribed 404, prompting the client to re-initialize. This MUST happen
only for genuinely expired/invalid sessions — never because a different replica answered or the gateway restarted
([ARC-10](../architecture/spec.md)).

#### Scenario: Unknown session id
- **WHEN** a request names an `Mcp-Session-Id` the store does not hold
- **THEN** the gateway answers HTTP 404

#### Scenario: Ending a session the gateway does not hold
- **WHEN** a `DELETE` names an unknown session id
- **THEN** the gateway answers 404, not 204

### Requirement: SES-3a Sessions belong to their endpoint and caller
A session belongs to the endpoint and the caller that opened it. A `POST`, `GET` or `DELETE` naming a session SHALL be
admitted like any other request first: an unknown endpoint is 404 and a missing or invalid credential gets the 401
challenge, both before the session is looked at. It is then served only when the session was opened on the endpoint in
the path **and** the authenticated caller has the same identity subject as the one that opened it (the same user, else
the same API key). Otherwise it is answered exactly like an unknown session (SES-3) — never 403, so a session id cannot
be probed for existence or used by anyone it leaks to.

#### Scenario: Unauthenticated DELETE
- **WHEN** a `DELETE` names a valid session id but carries no credential
- **THEN** the gateway answers the 401 challenge and the session still exists

#### Scenario: Session used through another endpoint
- **WHEN** a session opened on endpoint `main` is named on a request to another endpoint
- **THEN** the gateway answers 404 as for an unknown session

#### Scenario: Another caller holds the session id
- **WHEN** a different authenticated API key sends a request naming the session
- **THEN** the gateway answers 404 and the session is neither used nor ended

### Requirement: SES-4 Explicit session termination
Explicit `DELETE …/mcp` SHALL terminate the session and release its upstream bindings, subject to SES-3a. A `DELETE`
(or `GET`) without an `Mcp-Session-Id` is answered 405 ([EP-1](../endpoints/spec.md)).

#### Scenario: DELETE ends the session
- **WHEN** the owning caller sends `DELETE /main/mcp` with the session id
- **THEN** the record is removed and a later request naming the id gets 404

#### Scenario: DELETE or GET without a session id
- **WHEN** a client sends `GET` or `DELETE` to `/main/mcp` without `Mcp-Session-Id`
- **THEN** the gateway answers 405

### Requirement: SES-6 Upstream binding bookkeeping
A handshake-era session SHALL bind lazily, on its first call to each member server, to one upstream session for that
server, and record the binding in the session record: the server name, the upstream session id the upstream issued
(none for a modern-era upstream, which has no sessions), and the binding's identity key
([AUTH-31](../auth/spec.md)). Later requests of the session to that server, on any replica,
use the bound upstream session (SES-5). When the server forwards caller headers
([AUTH-31](../auth/spec.md)), uses `per_user` upstream OAuth
([UPS-26](../upstreams/spec.md)) or delegated tokens
([AUTH-32](../auth/spec.md)), the binding is keyed by the caller's identity and MUST never
be shared across identities. A binding's upstream session serves only the session that bound it; requests that carry
no binding — modern-era requests and discovery — use pooled upstream sessions, which for an identity-free server MAY be
shared between callers and for any other server are keyed by the caller's identity. A modern-era request records no
binding.

#### Scenario: First call records a binding
- **WHEN** a handshake-era client makes its first `tools/call` to a tool of server `echo`
- **THEN** the session record holds a binding for `echo` with the upstream session id `echo` issued and the identity key

#### Scenario: Later calls reuse the bound upstream session
- **WHEN** the same session calls a tool of `echo` a second time
- **THEN** the upstream request carries the bound upstream session id and no new `initialize` is sent

#### Scenario: Identity-bound sessions are never shared
- **GIVEN** server `crm` forwards the caller's `authorization` header
- **WHEN** users A and B each call a `crm` tool
- **THEN** each call runs on an upstream session opened with that caller's own header, and neither session serves the
  other caller

#### Scenario: Identity-free sessions may be shared
- **GIVEN** server `echo` forwards no caller headers and uses no per-user credentials
- **WHEN** two different modern-era callers call `echo` one after the other on the same replica
- **THEN** both calls may be served by the same pooled upstream session

#### Scenario: Modern request binds nothing
- **WHEN** a modern-era client calls a tool
- **THEN** no session record is read or written

### Requirement: SES-7 Upstream failure handling
When an upstream answers 404 for the upstream session a request names, or the transport to it is lost, the gateway SHALL
re-initialize the upstream session, rebind (updating the session record's binding) and retry the in-flight request
**once**, reusing the call's metering idempotency key without a second pre-call
([PROT-26](../protocol/spec.md)). A `tools/call` is retried only when the upstream did not run it — a 404
for its session, or a connection that failed before the request was sent; read-only requests are retried on any
transport loss. When the retry fails too, or the upstream is unreachable, fails with an exception or exceeds the call's
timeout, the gateway SHALL answer a structured MCP error (code `-32000`) rather than an HTTP failure, record the call as
an error in the audit log, and count the failure toward the server's health status
([UPS-4](../upstreams/spec.md)).

#### Scenario: Upstream restarted between calls
- **GIVEN** a handshake session bound to server `echo`, and `echo` restarted since, forgetting its sessions
- **WHEN** the client calls an `echo` tool
- **THEN** the upstream's 404 is answered by re-initializing, the binding is updated with the new upstream session id,
  and the client receives the tool's result
- **AND** the metering hook saw one `pre_call` and one `post_call`

#### Scenario: Repeated failure
- **WHEN** the retry after a re-initialize fails as well
- **THEN** the client receives a JSON-RPC error with code `-32000`, an audit record with status `error` is written, and
  the failure counts toward `echo`'s health status

#### Scenario: Connection lost after the call was sent
- **WHEN** the transport drops after a `tools/call` request reached the upstream and before its result
- **THEN** the call is not retried and the client receives a JSON-RPC error with code `-32000`

#### Scenario: Upstream unreachable
- **WHEN** a client calls a tool whose upstream refuses connections
- **THEN** the client receives a JSON-RPC error with code `-32000`
- **AND** an audit record with status `error` is written

### Requirement: SES-10 Idle session expiry
Sessions SHALL expire after `session_lifetime` seconds without activity — a runtime-configurable key (`Config`),
default 86400 (24 hours); `0` disables idle expiry, so sessions live until explicitly terminated (SES-4). A periodic
sweeper, run by one replica at a time, SHALL expire sessions idle beyond the lifetime: it removes the record, releases
the session's upstream bindings (SES-6) and counts the expiry. The
store's TTL on the record is the backstop, so a session expires even when no sweeper runs. A changed lifetime applies to
each session from its next activity.

#### Scenario: Idle session expires
- **WHEN** no request names a session for longer than the session lifetime
- **THEN** its record has expired and a request naming it gets 404

#### Scenario: Sweeper releases the bindings
- **GIVEN** an idle session bound to upstream server `echo`
- **WHEN** the sweeper runs after the session's lifetime has passed
- **THEN** the record is removed, its upstream binding is released and the expiry is counted

#### Scenario: No idle expiry
- **WHEN** `session_lifetime` is `0` and a session stays idle for longer than 24 hours
- **THEN** the session still serves requests until it is deleted

#### Scenario: Sweeper runs once across replicas
- **WHEN** two replicas are running when a sweep is due
- **THEN** only one of them sweeps

### Requirement: SES-11 Sessions survive shutdown
Shutting a replica down SHALL be graceful and bounded. On SIGTERM the replica reports not ready, refuses new requests,
lets in-flight requests finish for at most a configurable drain window (`BUNDLEMCP_SHUTDOWN_DRAIN_SECONDS`), ends every
open notification stream it holds cleanly (see [PROT-17](../protocol/spec.md)), answers any
call still running at the deadline with a structured error and reports it to metering as `cancelled`, then exits. In the
container image the signal MUST reach the gateway process itself. Session records SHALL persist in the RESP store across
the shutdown — clients continue on other replicas or after restart without re-initializing.

#### Scenario: Restart keeps the session
- **WHEN** the gateway is restarted while a client holds a session
- **THEN** the client's next request on that session id succeeds without `initialize`

#### Scenario: In-flight call drains
- **WHEN** a replica receives SIGTERM while a tool call that takes 2 seconds is in flight and the drain window is 10 s
- **THEN** the call completes with its result and the process exits afterwards, before the window ends

#### Scenario: Drain window runs out
- **WHEN** a call is still running when the drain window ends
- **THEN** the client receives a structured error and the metering hook's `post_call` receives outcome `cancelled`

#### Scenario: Container stop is graceful
- **WHEN** `docker compose stop gateway` runs with the default grace period
- **THEN** the gateway logs its shutdown and exits by itself, without being killed at the end of the grace period

### Requirement: SES-12 Integration tests
Integration tests against the compose stack MUST cover: restart under load (sessions survive a gateway restart while
clients keep sending requests, with no request answered 404 or 500), two-replica round-robin (requests on one session
alternate between two gateway replicas and all succeed), upstream-restart recovery (an upstream restarted between two
calls of a session costs no client-visible error — SES-7), and a Valkey
restart (the gateway reconnects and a lost session costs one re-initialize, never a 500). Hermetic tests MUST cover
cross-replica behavior with two app instances sharing one store.

#### Scenario: Restart integration test
- **WHEN** clients send requests on open sessions continuously while the gateway restarts
- **THEN** after the gateway is ready again every session serves `tools/list` without re-initializing, and no request
  was answered 404 or 500

#### Scenario: Two-replica round-robin
- **WHEN** the suite runs two gateway replicas behind a round-robin proxy and sends ten requests on one session
- **THEN** both replicas served requests and all ten succeeded

#### Scenario: Upstream restart recovery
- **WHEN** an upstream server is restarted between two tool calls of one session
- **THEN** the second call returns the tool's result

#### Scenario: Two app instances
- **WHEN** a hermetic test runs two app instances on one Postgres and one store
- **THEN** a change made through one instance reaches a stream held by the other

### Requirement: SES-13 Cross-replica delivery
Live streams (a handshake client's GET event stream, a modern client's `subscriptions/listen` stream, an in-flight
call's response stream, a parked call) are pinned to the replica holding them; everything else is not. Each
notification stream SHALL be registered under a **stream key** — endpoint, bundle and a stream id that is the session
id for handshake clients and the request's routing key for modern ones — so list-changed fan-out selects streams by
endpoint or bundle without loading a session. Messages that must reach a specific stream or call from another replica —
cancellations, list-changed notifications, server→client requests and their responses, MRTR resumes and results
([protocol](../protocol/spec.md)) — SHALL be routed via RESP pub/sub channels
(`bmcp:signal:{key}`) keyed by stream id, routing key or correlation id, delivered by the replica holding the target.
A request for a target with no live holder anywhere SHALL fail fast with a structured error instead of waiting for an
answer; a notification for such a target is dropped.

#### Scenario: Cancellation reaches another replica
- **WHEN** a call runs on replica A and `notifications/cancelled` for it arrives at replica B
- **THEN** B publishes the cancel signal and A cancels the upstream call

#### Scenario: List change reaches a stream on another replica
- **WHEN** a modern client holds a `subscriptions/listen` stream on replica B and the bundle is changed through A
- **THEN** the stream on B receives `notifications/tools/list_changed`

#### Scenario: No holder for a server→client request
- **WHEN** an upstream asks for elicitation during a handshake client's call and no replica holds that client's GET
  stream
- **THEN** the upstream's request is refused within a second and the call ends with a structured error, without waiting
  for the call timeout

### Requirement: SES-14 Degradation matrix
The gateway SHALL behave as follows under these failures:

| Failure | Behavior |
|---|---|
| **Redis down** | Requests that need the store → 503 + `Retry-After` (no false 404s); after recovery, records with intact TTLs resume, otherwise clients re-`initialize`. Rate limits per [EP-21](../endpoints/spec.md). Admin UI logins unavailable; `readyz` false. |
| **Redis restarted** | Pooled connections that died with the old instance are replaced inside the request (bounded retry with backoff; idle connections are health-checked before reuse), so no request fails only because its connection is stale. A session the restart lost answers the ordinary `404` re-initialize signal, never a `500`. If the store is still unreachable after the retries, the Redis-down row applies. |
| **Postgres down** | Token and key validation fails closed: a request that needs a credential checked or configuration read answers 503 + `Retry-After` (a JSON-RPC error on MCP endpoints), never 401 for a valid credential and never an unhandled 500. Config mutations answer 503; audit writes are buffered by the in-process audit queue ([OPS-3](../operations/spec.md)); `readyz` false. |
| **Single replica dies** | Its pinned streams drop; clients retry/reconnect and any replica serves them (SES-2); in-flight calls on that replica surface to their clients as retryable errors. |

#### Scenario: Store unreachable
- **WHEN** Valkey cannot be reached while a session request is served
- **THEN** the gateway answers 503 with a `Retry-After` header, not 404 and not 500

#### Scenario: Store restarted
- **WHEN** Valkey restarts with the gateway's pooled connections open
- **THEN** the next request reconnects and is served, and a session lost with the restart answers 404

#### Scenario: Postgres unreachable
- **WHEN** Postgres cannot be reached and a client sends `tools/list` with a valid API key
- **THEN** the gateway answers 503 with a `Retry-After` header, not 401 and not 500

#### Scenario: Config change while Postgres is down
- **WHEN** an admin sends `PUT /api/v1/upstreams/echo` while Postgres cannot be reached
- **THEN** the management API answers 503

### Requirement: SES-15 Stateless modern-era requests
A request carrying `_meta["io.modelcontextprotocol/protocolVersion"]` SHALL be admitted on its own: the caller identity
is resolved from its credentials, the protocol version, client capabilities and log level are read from `_meta`, and a
per-request routing key replaces the session id for in-flight bookkeeping (cancellation, progress, parked calls). No
record is written to the store and no `Mcp-Session-Id` is minted or echoed; one present on the request is ignored. Any
replica serves any modern request without lookup ([ARC-9](../architecture/spec.md)).

#### Scenario: Modern request writes no session
- **WHEN** a modern-era client sends `tools/list` with the `_meta` envelope
- **THEN** the response carries no `Mcp-Session-Id` header and no session record is written

#### Scenario: Stray session header ignored
- **WHEN** a modern-era request also carries an `Mcp-Session-Id` header naming no session
- **THEN** it is served statelessly instead of answered 404

### Requirement: SES-16 Parked calls
A **parked call** ([PROT-18](../protocol/spec.md) park and resume) is the one modern-era object that is
replica-pinned: the in-flight upstream call waiting for the client's retry. It SHALL be registered on its replica under
the correlation id sealed into `requestState`, live at most for the call's remaining PROT-2 budget, and be reached from
any replica via the SES-13 signal bus. A retry that no replica claims within a short grace period falls back to a re-run
(PROT-18); a replica that dies loses only the parked calls it held, exactly as it loses its live streams.

#### Scenario: Retry lands on another replica
- **WHEN** a call is parked on replica A and the client's retry reaches replica B
- **THEN** B routes the answers to A over the signal bus and streams the call's result to the client

#### Scenario: Parking replica is gone
- **WHEN** a retry names a correlation id no replica holds
- **THEN** after the grace period the call is re-run with the client's answers pre-loaded and returns a result

### Requirement: SES-17 Invalidation event on every config mutation
Every mutation of configuration state — `McpServer`, bundle membership, `BundleTool` curation, `Endpoint`, `ApiKey`,
runtime `Config` keys — MUST publish an invalidation event (`{entity_type, key, action}`, where `key` is the natural
key or id) on the well-known RESP pub/sub channel `bmcp:invalidate` after the Postgres commit.

#### Scenario: Upsert announces the change after commit
- **WHEN** a server is upserted twice through the management service
- **THEN** each commit publishes one `server` invalidation event, and none is published for a rolled-back change

#### Scenario: Config key change
- **WHEN** an operator sets `call_timeout` through `PUT /api/v1/config/call_timeout`
- **THEN** a `config` event with key `call_timeout` is published after the commit

### Requirement: SES-18 Replicas subscribe and flush
Replicas SHALL subscribe from startup; on event receipt they MUST invalidate the affected local cache entries. On
(re)connect to the store after a gap, a replica MUST flush all config caches (it may have missed events).

#### Scenario: Event flushes the runtime config cache
- **WHEN** a replica receives a `config` invalidation event
- **THEN** its runtime config cache is dropped and the next read loads the stored values

#### Scenario: Resubscribe after a gap
- **WHEN** a replica's subscription to the invalidation channel is lost and re-established
- **THEN** it flushes its config caches before dispatching further events

### Requirement: SES-19 Propagation budget
A config change MUST be effective on all replicas within **2 seconds** under normal operation. Integration tests against
the compose stack with two gateway replicas SHALL assert this for at least endpoint disable
([EP-5](../endpoints/spec.md)), API key deactivation ([AUTH-25](../auth/spec.md)) and
tool disable ([BND-13](../bundles/spec.md)), each changed through one replica and observed through
the other.

#### Scenario: Runtime config change reaches another replica
- **WHEN** an operator changes a config key through replica A while replica B has the old value cached
- **THEN** B serves the new value within 2 seconds, driven by the invalidation event and not by a TTL

#### Scenario: Endpoint disable within the budget
- **WHEN** an endpoint is disabled through replica A
- **THEN** within 2 seconds a request to it through replica B is answered 404

#### Scenario: Key deactivation within the budget
- **WHEN** an API key is deactivated through replica A
- **THEN** within 2 seconds a request presenting it through replica B is answered 401

#### Scenario: Tool disable within the budget
- **WHEN** a tool is disabled in its bundle through replica A
- **THEN** within 2 seconds `tools/list` through replica B no longer lists it and a call to it is rejected

### Requirement: SES-20 API-key cache only with invalidation
API-key semantics reconciled: [AUTH-26](../auth/spec.md)'s store/local validation cache is permitted **only** in
combination with SES-17 invalidation on deactivate/delete — "immediately" in AUTH-25 SHALL mean within the SES-19
budget, never "when a TTL happens to expire".

#### Scenario: Deactivated key is refused at once
- **WHEN** an API key is deactivated through the management API
- **THEN** a request presenting it on any replica within the SES-19 budget is refused with 401

### Requirement: SES-22 Caching is never a correctness dependency
Caching is an optimization, never a correctness dependency. The only per-replica configuration cache SHALL be the
runtime `Config` cache; endpoint lookups, bundle composition and API-key validation are read from Postgres on every
request, so their changes take effect on the next request on every replica. A debugging setting
(`BUNDLEMCP_CONFIG_CACHE_DISABLED`) SHALL disable every configuration cache; with it set, behaviour MUST be identical,
only slower.

#### Scenario: Endpoint disable takes effect on the next request
- **WHEN** an endpoint is disabled through the management API
- **THEN** the next request to it on any replica is answered 404

#### Scenario: Caching disabled
- **WHEN** the gateway runs with `BUNDLEMCP_CONFIG_CACHE_DISABLED` set and an operator changes `call_timeout`
- **THEN** the next call on any replica uses the new value, with no invalidation event needed

#### Scenario: Same behaviour without the cache
- **WHEN** the hermetic test suite's runtime-config tests run with caching disabled
- **THEN** they pass unchanged

### Requirement: SES-5 Upstream sessions are data
An upstream Streamable HTTP session that a binding names (SES-6) SHALL be represented in the RESP store by its upstream
session id, the server's endpoint URL and a fingerprint of the headers it was opened with, so any replica can continue
it. Header values MUST
never be stored: a replica rebuilds them from the server's configuration and the request it serves. Live HTTP
connections are per-replica transport details; losing one MUST NOT lose the upstream session when the upstream is
spec-compliant.

#### Scenario: Upstream session continues on another replica
- **WHEN** a handshake-era session's first call to server `echo` is served by replica A and its second by replica B
- **THEN** B's upstream request carries the upstream session id A obtained
- **AND** the upstream receives no second `initialize`

#### Scenario: Header values are not stored
- **WHEN** a binding is recorded for a server that forwards the caller's `authorization` header
- **THEN** the stored binding holds the upstream session id and a header fingerprint, and no header value

#### Scenario: Lost connection, kept session
- **WHEN** the replica holding a pooled connection to a spec-compliant upstream restarts between two calls
- **THEN** the next call reuses the stored upstream session id without re-initializing

### Requirement: SES-8 Upstream connection caps
Each replica SHALL cap the upstream sessions it holds open, globally and per server, with runtime-configurable limits
(`upstream_sessions_max`, `upstream_sessions_per_server_max`). At a cap it evicts the least-recently-used idle
identity-free pooled session first, then idle identity-bound ones; when nothing is evictable the call is served on a
connection opened for that call alone and closed after it. Upstream sessions are opened on demand, never pre-warmed.

#### Scenario: Identity-free sessions are evicted first
- **GIVEN** `upstream_sessions_max` is 2 and a replica holds one idle identity-free and one idle identity-bound session
- **WHEN** a call needs a third upstream session
- **THEN** the identity-free session is closed and the identity-bound one is kept

#### Scenario: Nothing evictable
- **GIVEN** every pooled session on the replica is in use and the cap is reached
- **WHEN** another call arrives
- **THEN** it is served on a connection of its own that is closed when the call ends, and the call succeeds

#### Scenario: Cap change applies without restart
- **WHEN** an operator lowers `upstream_sessions_per_server_max` through the config API
- **THEN** each replica closes idle sessions above the new cap within the propagation budget

### Requirement: SES-9 Config changes invalidate pooled sessions
A configuration change to a server ([UPS-6](../upstreams/spec.md)) SHALL invalidate its pooled
upstream sessions on every replica via the invalidation event stream
([sessions](../sessions/spec.md)): each replica closes that server's idle transports at
once and in-use ones when their call ends, and a binding made under the previous configuration is re-established on its
next use instead of reused.

#### Scenario: URL change drops pooled transports everywhere
- **GIVEN** replicas A and B each hold a pooled session to server `echo`
- **WHEN** `echo`'s URL is changed through replica A
- **THEN** within the propagation budget neither replica holds a transport to the old URL
- **AND** the next call through either replica opens a session to the new URL

#### Scenario: Stale binding is re-established
- **WHEN** a handshake session bound to `echo` calls it again after `echo`'s headers changed
- **THEN** the call opens a new upstream session and the session record's binding names it

### Requirement: SES-21 Server invalidation tears down pooled transports
A `server` invalidation event SHALL additionally tear down that server's pooled upstream transports on every replica
([SES-9](../sessions/spec.md)), riding the same event stream and within the SES-19 budget. A
replica that resubscribes after a gap SHALL tear down all its pooled upstream transports, as it flushes its config
caches (SES-18), since it may have missed a server event.

#### Scenario: Server event closes another replica's transports
- **GIVEN** replica B holds an idle pooled transport to server `echo`
- **WHEN** `echo` is updated through replica A
- **THEN** B closes that transport within 2 seconds of the commit

#### Scenario: Resubscribe after a gap
- **WHEN** a replica's subscription to the invalidation channel is lost and re-established
- **THEN** it closes every pooled upstream transport it holds before dispatching further events

## Out of scope

### Session management

- Resumability/redelivery of streamed responses across replicas (`Last-Event-ID` replay). Session continuity is
  guaranteed, not mid-stream event replay; a lost stream surfaces as a retryable request.
- Sticky-session load-balancer requirements — explicitly rejected; the design goal is NO stickiness.

### State propagation

- Cache coherence for *data* state (tool cache freshness is [upstreams](../upstreams/spec.md)'s concern;
  sessions are [sessions](../sessions/spec.md)'s).

## Notes

### Session management

Origin: new — the architectural fix for metamcp's #1 failure mode (sessions bound to process memory: restart 404
storms, no horizontal scaling, a recovery subsystem to paper over it).

The client-facing endpoint edge is implemented directly on FastAPI with session records in the RESP store; FastMCP
serves the upstream client side only ([ADR-0011](../../../docs/adr/0011-own-streamable-http-edge.md)). Upstream
connections are per call ([ADR-0012](../../../docs/adr/0012-per-call-upstream-connections.md)); upstream session
pooling, connection caps and pool invalidation are not built.

### State propagation

Origin: new — generalizes upstream pool invalidation and fixes the AUTH-25/AUTH-26 contradiction. The invalidation bus
(`bmcp:invalidate`, one channel) is separate from the cross-replica signal bus (`bmcp:signal:*`,
[SES-13](../sessions/spec.md)). Besides flushing runtime config, `bundle` and `endpoint` events drive the
`list_changed` notifications of [BND-7](../bundles/spec.md).
