## MODIFIED Requirements

### Requirement: SES-6 Upstream binding bookkeeping
A handshake-era session SHALL bind lazily, on its first call to each member server, to one upstream session for that
server, and record the binding in the session record: the server name, the upstream session id the upstream issued
(none for a modern-era upstream, which has no sessions), and the binding's identity key
([AUTH-31](../../../../specs/auth/spec.md)). Later requests of the session to that server, on any replica,
use the bound upstream session (SES-5). When the server forwards caller headers
([AUTH-31](../../../../specs/auth/spec.md)), uses `per_user` upstream OAuth
([UPS-26](../../../../specs/upstreams/spec.md)) or delegated tokens
([AUTH-32](../../../../specs/auth/spec.md)), the binding is keyed by the caller's identity and MUST never
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
([PROT-26](../../../../specs/protocol/spec.md)). A `tools/call` is retried only when the upstream did not run it — a 404
for its session, or a connection that failed before the request was sent; read-only requests are retried on any
transport loss. When the retry fails too, or the upstream is unreachable, fails with an exception or exceeds the call's
timeout, the gateway SHALL answer a structured MCP error (code `-32000`) rather than an HTTP failure, record the call as
an error in the audit log, and count the failure toward the server's health status
([UPS-4](../../../../specs/upstreams/spec.md)).

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

## ADDED Requirements

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
A configuration change to a server ([UPS-6](../../../../specs/upstreams/spec.md)) SHALL invalidate its pooled
upstream sessions on every replica via the invalidation event stream
([sessions](../../../../specs/sessions/spec.md)): each replica closes that server's idle transports at
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
([SES-9](../../../../specs/sessions/spec.md)), riding the same event stream and within the SES-19 budget. A
replica that resubscribes after a gap SHALL tear down all its pooled upstream transports, as it flushes its config
caches (SES-18), since it may have missed a server event.

#### Scenario: Server event closes another replica's transports
- **GIVEN** replica B holds an idle pooled transport to server `echo`
- **WHEN** `echo` is updated through replica A
- **THEN** B closes that transport within 2 seconds of the commit

#### Scenario: Resubscribe after a gap
- **WHEN** a replica's subscription to the invalidation channel is lost and re-established
- **THEN** it closes every pooled upstream transport it holds before dispatching further events
