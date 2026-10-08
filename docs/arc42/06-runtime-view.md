# 6. Runtime View

Three load-bearing scenarios (normative details in the linked specs).

## 6.1 claude.ai connects to an endpoint (OAuth 2.1)

1. Client hits `/{endpoint}/mcp` unauthenticated → 401 + protected-resource metadata
   ([EP-3](../../spec/14-endpoints.md)).
2. Client registers via `POST /oauth/register` (DCR) and starts `GET /oauth/authorize` (PKCE, `resource` = endpoint
   URL).
3. Gateway has no session → redirects the user to the OIDC IdP; on return the user is provisioned
   ([ADM-2](../../spec/21-admin-auth.md)) and sees the **consent screen** ([OAS-11](../../spec/20-oauth-server.md)).
4. Code → token exchange; the access token's audience is the endpoint ([OAS-10](../../spec/20-oauth-server.md)). Client
   initializes; session record created in Redis ([SES-1](../../spec/30-session-management.md)).
5. Refresh rotates tokens; introspection exposes `sub` + audience to upstreams/app layer.

## 6.2 Tool call with metering, progress, and refund-on-failure

1. `tools/call` arrives at **any** replica; session loaded from Redis; identity from the bearer (EP-6).
2. Middleware chain: tool enabled? → override reverse-map → profile check → **metering pre-call**
   (`{sub, email, bundle, server, tool, idempotency_key}`) — deny ends the call with a structured error
   ([MID-3](../../spec/31-middleware.md)).
3. Prefix parsed (first `__`), upstream binding resolved or lazily created (identity-keyed when headers are forwarded,
   [FWD-5](../../spec/24-identity-forwarding.md)).
4. Upstream call runs with progress-aware timeouts; `notifications/progress` relayed to the client
   ([PROT-1/2](../../spec/32-protocol-passthrough.md)). A client cancel reaching another replica is routed via pub/sub
   ([PROT-3](../../spec/32-protocol-passthrough.md), SES-13).
5. Result → **metering post-call** with the outcome (`result`, `tool_error`, `no_result` or `cancelled`; the hook
   decides what each costs) → audit record
   ([AUD-1/7](../../spec/50-audit-log.md)).

## 6.3 Gateway restart under load (the metamcp fix)

1. Replica receives SIGTERM: stops accepting, drains in-flight (SES-11), exits.
2. Session records persist in Redis; nothing is "lost" with the process.
3. Client's next request lands on another replica (or the restarted one), which loads the session record and serves —
   **no 404, no re-initialize** (SES-2/3). Its pinned streams reconnect; upstream bindings re-establish lazily
   (SES-5/7).
4. Verified continuously by the restart-under-load and two-replica integration tests (SES-12, DEP-7).

## 6.4 Long-running call with progress, then a cross-replica cancel

1. Client sends `tools/call` with `_meta.progressToken`; the gateway replies `text/event-stream` and runs the upstream
   call as a task under a watchdog (PROT-1/2). A `CallHandle` is registered in this replica's StreamRegistry.
2. The upstream emits `notifications/progress`; each is relayed as an SSE event and resets the idle timeout
   (reset-on-progress).
3. The client's `notifications/cancelled` lands on **another replica**. That replica publishes a `cancel` signal on the
   Redis bus ([ADR-0016](../adr/0016-relay-design.md), SES-13); the replica holding the `CallHandle` sets its cancel
   event, the upstream task is cancelled, and the SSE stream emits a JSON-RPC error. Metering
   `post_call(status=error)` + audit record fire (MID-3).
4. If instead the upstream raises `elicitation/create`, it is delivered on the client's GET event stream (possibly on a
   third replica) and the client's reply routed back by correlation id — capability-gated (PROT-4/5/6).
