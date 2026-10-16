# 6. Runtime View

Three load-bearing scenarios (normative details in the linked specs).

## 6.1 claude.ai connects to an endpoint (OAuth 2.1)

1. Client hits `/{endpoint}/mcp` unauthenticated → 401 + protected-resource metadata
   ([EP-3](../../openspec/specs/endpoints/spec.md)).
2. Client registers via `POST /oauth/register` (DCR) and starts `GET /oauth/authorize` (PKCE, `resource` = endpoint
   URL).
3. Gateway has no session → redirects the user to the OIDC IdP; on return the user is provisioned
   ([AUTH-16](../../openspec/specs/auth/spec.md)) and sees the **consent screen**
   ([AUTH-11](../../openspec/specs/auth/spec.md)).
4. Code → token exchange; the access token's audience is the endpoint
   ([AUTH-10](../../openspec/specs/auth/spec.md)). Client initializes; session record created in Redis
   ([SES-1](../../openspec/specs/sessions/spec.md)).
5. Refresh rotates tokens; introspection exposes `sub` + audience to upstreams/app layer.

## 6.2 Tool call with metering, progress, and refund-on-failure

1. `tools/call` arrives at **any** replica; session loaded from Redis; identity from the bearer (EP-6).
2. Middleware chain: tool enabled? → override reverse-map → profile check → **metering pre-call**
   (`{sub, email, bundle, server, tool, idempotency_key}`) — deny ends the call with a structured error
   ([PROT-26](../../openspec/specs/protocol/spec.md)).
3. Prefix parsed (first `__`); the call leases the upstream session bound to the client's session — continued from
   the binding's upstream session id without `initialize`, on any replica, or opened and bound on the first call
   (identity-keyed when headers are forwarded, [AUTH-31](../../openspec/specs/auth/spec.md),
   [SES-5/6](../../openspec/specs/sessions/spec.md)). A 404 for that session re-initializes, rebinds and retries once
   under the same idempotency key (SES-7).
4. Upstream call runs with progress-aware timeouts; `notifications/progress` relayed to the client
   ([PROT-1/2](../../openspec/specs/protocol/spec.md)). A client cancel reaching another replica is routed
   via pub/sub ([PROT-3](../../openspec/specs/protocol/spec.md), SES-13).
5. Result → **metering post-call** with the outcome (`result`, `tool_error`, `no_result` or `cancelled`; the hook
   decides what each costs) → audit record
   ([OPS-1/7](../../openspec/specs/operations/spec.md)).

## 6.3 Gateway restart under load (the metamcp fix)

1. Replica receives SIGTERM (the image `exec`s the gateway, so the signal reaches it). It starts draining (SES-11):
   `/readyz` and new MCP requests answer `503` with `Retry-After`, every notification stream it holds ends, and the
   load balancer has two seconds to notice before connections close.
2. In-flight calls finish within `BUNDLEMCP_SHUTDOWN_DRAIN_SECONDS`; one still running just before the window ends is
   cancelled through its handle, answers with an error and is metered `cancelled`. Then the process exits.
3. Session records persist in Redis; nothing is "lost" with the process.
4. Client's next request lands on another replica (or the restarted one), which loads the session record and serves —
   **no 404, no re-initialize** (SES-2/3). Its pinned streams reconnect; upstream bindings re-establish lazily
   (SES-5/7).
5. Verified by the integration suite on two replicas behind a round-robin proxy
   (`deploy/docker-compose.replicas.yml`): restart under load and a rolling update of a new image, neither answering
   any request `404` or `500` (SES-12, DEP-7).

## 6.3a An idle session expires

1. Every request on a session, and every keep-alive of its open GET stream, records `last_active_at` and indexes the
   session by it; the record's TTL is `session_lifetime` plus two sweep intervals (SES-1).
2. Once a minute one replica takes the sweep lease and removes every session idle past `session_lifetime`, checking
   each record before it goes, and logs `session.expired` (SES-10).
3. If no replica sweeps, the TTL removes the record. A request naming an expired session gets `404` and the client
   re-initializes. `session_lifetime = 0` keeps sessions until they are deleted.

## 6.4 Long-running call with progress, then a cross-replica cancel

1. Client sends `tools/call` with `_meta.progressToken`; the gateway replies `text/event-stream` and runs the upstream
   call as a task under a watchdog (PROT-1/2). A `CallHandle` is registered in this replica's StreamRegistry under the
   request's call key and request id: the session for a handshake client, the endpoint and caller for a modern one
   (PROT-3), so a modern client cancels from a request of its own and nobody else can.
2. The upstream emits `notifications/progress`; each is relayed as an SSE event and resets the idle timeout
   (reset-on-progress).
3. The client's `notifications/cancelled` lands on **another replica**. That replica publishes a `cancel` signal on the
   Redis bus ([ADR-0016](../adr/0016-relay-design.md), SES-13); the replica holding the `CallHandle` sets its cancel
   event, the upstream task is cancelled, and the SSE stream emits a JSON-RPC error. Metering
   `post_call` with outcome `cancelled` + audit record fire (PROT-26). A client that closes the stream, or disconnects
   while it waits for a buffered (non-streamed) result, cancels the call the same way.
4. If instead the upstream raises `elicitation/create`, it is delivered on the client's GET event stream (possibly on a
   third replica) and the client's reply routed back by correlation id — capability-gated (PROT-4/5/6).

## 6.5 A member's notification between calls

1. Replica A holds a pooled upstream session to member `echo`: the SDK's GET stream for a handshake upstream, a
   standing `subscriptions/listen` for a modern one ([ADR-0054](../adr/0054-upstream-session-pooling.md)).
2. `echo` sends `notifications/tools/list_changed` while no call is in flight. `UpstreamNotificationRouter` takes the
   Valkey gate `bmcp:rediscover:echo:tools` (`SET NX EX`); a replica B hearing the same change on its own session
   finds the gate taken and stands down ([PROT-10](../../openspec/specs/protocol/spec.md)).
3. A re-discovers `echo` and invalidates its bundles; every replica's `ListChangedNotifier` tells the GET and listen
   streams it holds (BND-7).
4. A `notifications/resources/updated` instead goes to the streams the Valkey subscription index lists for that URI,
   and a log message on a session bound to a client's session to that client's GET stream, through the signal bus to
   whichever replica holds the stream ([PROT-7/23](../../openspec/specs/protocol/spec.md)).
