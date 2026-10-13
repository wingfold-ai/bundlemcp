## MODIFIED Requirements

### Requirement: SES-1 Session record on initialize
SES-1 to SES-4 apply to clients that open with `initialize` (revisions 2025-11-25 and earlier). A modern-era request
SHALL never create, read or require a session record.

On `initialize`, the gateway SHALL create a session record in the RESP store keyed by the issued `Mcp-Session-Id`
(`bmcp:session:{id}`): endpoint, bundle, resolved caller identity, negotiated protocol version, the client's advertised
capabilities, the client's requested log level ([PROT-7](../protocol/spec.md)), the time the
session was created and the time of its last activity, and a record-schema `version` field
([DEP-6](../deployment/spec.md)). The record's TTL is the idle session lifetime, the runtime-configurable
`session_lifetime` (SES-10), refreshed together with the last-activity time on every request on the session (a `ping`
counts — [PROT-8](../protocol/spec.md)).

#### Scenario: Initialize writes a record and returns its id
- **WHEN** a handshake-era client sends `initialize` to `/main/mcp` with an API key
- **THEN** the response carries an `Mcp-Session-Id` header
- **AND** a record under `bmcp:session:{id}` holds endpoint `main`, its bundle, the caller identity, the negotiated
  protocol version and equal creation and last-activity times

#### Scenario: Activity refreshes the TTL
- **WHEN** a client sends `ping` on an existing session
- **THEN** the record's TTL is reset to the session lifetime and its last-activity time is the time of the `ping`

#### Scenario: Lifetime follows the runtime setting
- **WHEN** an operator sets `session_lifetime` to 3600 and a client then initializes
- **THEN** the new record's TTL is 3600 seconds

#### Scenario: A record of another schema version is treated as expired
- **WHEN** a stored record's `version` is not one this build reads
- **THEN** loading it deletes it and the request is answered like an unknown session

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
