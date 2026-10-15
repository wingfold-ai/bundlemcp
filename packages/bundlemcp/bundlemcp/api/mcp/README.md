# gateway — the MCP serving edge

This package is the core of bundlemcp: it terminates the client-facing Streamable-HTTP MCP protocol, composes a bundle's
tool surface, proxies calls to the right upstream server, and records what happened. The client edge is **hand-rolled**
(`routing/gateway_router.py`) rather than delegated to FastMCP's session manager, precisely so that session state lives
in the RESP store and any replica can serve any request (ARC-9/ARC-10). FastMCP is used only for the *upstream* leg.

## Package layout

The package is split by concern, so the serving machinery is self-evident next to the one method feature that owns a
package:

| Package | Holds |
|---|---|
| `routing/` | The front door: `McpGatewayRouter` (POST/GET/DELETE), the `AdmissionGate` pipeline, the era `adapters/`, the session SSE `session_stream.py`, and `authentication/` (who may call) |
| `protocol/` | The wire vocabulary: version-neutral JSON-RPC envelope, contexts, error helper, protocol version, log levels, server info, cache hints, forwarded headers, SSE framing, session header — and `dialect/`, the per-revision part of the same subject |
| `dispatch/` | The method surface: `MethodRegistry`, the `MethodHandler` contract, the rate-limiting decorator/gate, and `handlers/` (one class per JSON-RPC method) |
| `relay/` | Bidirectional server-to-client interaction: the open-stream `ClientRelay` and the stateless `input_required` retry machinery |
| `tool_call/` | The `tools/call` execution pipeline |
| `controllers/` | The FastAPI route class for `/{endpoint}/mcp` |
| `providers.py` | FastAPI dependency that resolves the router off the container |


Read [../oauth/README.md](../oauth/README.md) for how callers are authenticated; this doc picks up once a request is
authorized.

> **"the RESP store" = Valkey.** The live-state store ships as Valkey (BSD-3), a drop-in RESP server; the client is
> `redis-py` and the URL scheme stays `redis://`, so `redis`-named symbols, `bmcp:` keys, and "Redis pub/sub / server
> time" below refer to the RESP protocol the code speaks — see
> [the package README](../../../README.md#a-note-on-the-resp-store-valkey-not-redis-adr-0022)
> and ADR-0022.

---

## 0. Two protocol eras on one endpoint

MCP 2026-07-28 removed the `initialize` handshake, the `Mcp-Session-Id` session, the HTTP GET stream and
server-initiated requests. The edge serves that revision **and** the handshake revisions (2025-11-25 and earlier) on the
same URL, picking a *dialect* once per request (`protocol/dialect/`, PROT-13):

| Client opens with | Dialect | Where its facts come from |
|---|---|---|
| `params._meta["io.modelcontextprotocol/protocolVersion"]` | modern (2026-07-28) | the request itself: version, capabilities, log level; validated with the SDK's inbound ladder incl. `Mcp-Method`/`Mcp-Name`/`Mcp-Param-*` headers (PROT-15) |
| `initialize` | handshake, negotiated (PROT-12) | a session record written to the RESP store |
| `Mcp-Session-Id` | the session's handshake dialect | the session record |
| none of these | — | `400` / `-32602` naming the supported versions, so a dual-era client falls back |

Handlers see one `RequestContext` and call `ctx.shape(result)`; the dialect adds `resultType`, `_meta.serverInfo` and
`ttlMs`/`cacheScope` for modern clients and leaves handshake results untouched (PROT-16). Modern-only methods:
`server/discover` (PROT-14) and `subscriptions/listen` (PROT-17, a long-lived POST stream that replaces the GET stream;
`GET`/`DELETE` without a session id answer 405). Handshake-only: `ping`, `logging/setLevel`, `resources/subscribe`. A
modern `tools/call` is always streamed, so a client disconnect is its cancellation (PROT-19). When an upstream asks for
client input during a modern client's call, `relay/` turns it into an `input_required` result the client answers by
retrying: pass-through of the upstream's own result for a modern upstream, park-and-resume over the signal bus for a
handshake upstream, re-run as the fallback (PROT-18). The upstream leg negotiates its own era per server
(`McpServer.protocol_mode`, PROT-21). The lifecycle below shows a handshake client; a modern request skips the session
steps.

## 1. The request lifecycle

A `tools/call` to `POST /{endpoint_name}/mcp` (`routing/gateway_router.py::McpGatewayRouter.post`) travels through these
stages. Each is a named class or method you can grep for.

```
HTTP POST /{endpoint}/mcp
  │
  ├─ McpGatewayRouter.post                     size gate (Content-Length) → 413
  ├─ AdmissionGate.parse_envelope              JSON-RPC envelope, pure CPU
  ├─ AdmissionGate.admit_caller                one unit of work:
  │     ├─ load_bundle_view(uow, endpoint)     application/serving/bundle_view_loader.py — 404 if missing/disabled
  │     └─ EndpointAuthentication.authenticate OAuth bearer, else API key, else none
  │           └─ miss → AuthFailureGuard → 401 + WWW-Authenticate (RFC 9728) or 429
  ├─ SessionMcpAdapter / StatelessMcpAdapter   era: session record (Valkey) or the request's own _meta
  ├─ MethodRegistry → RateLimited(ToolsCallHandler)   429 short-circuit (§6)
  └─ ToolsCallHandler → ToolCall.run           tool_call/tool_call.py
        ├─ view.resolve(presented_name)        unknown/disabled → DENIED + error
        ├─ _resolve_headers                    forwarded headers, then the upstream OAuth bearer —
        │                                      BEFORE metering, so unconnected ≠ debited
        ├─ _meter_pre_call                     deny → DENIED + error
        ├─ execute → UpstreamCall.run          per-call FastMCP client → call_tool_mcp
        │     └─ reactive OAuth retry once on upstream 401 (UPS-28)
        └─ finish → _post_call + _record       metering settlement + audit → JSON-RPC result/error
```

Key points that are easy to miss:

- **`initialize` never touches upstreams.** It negotiates the protocol version (`protocol/protocol_version.py`), mints a
  session id, and returns aggregated capabilities from the cached per-server `capabilities` snapshot (PROT-11). The
  session record is written to Redis here and the id is returned in the `Mcp-Session-Id` response header.
- **Auth precedence is OAuth then API key.** OAuth validation is a direct DB lookup on
  `OAuthAccessToken.access_token_hash`, checking `revoked`, expiry, and **audience**
  (`row.endpoint_id == view.endpoint.id`, EP-3a) — a token minted for one endpoint cannot be replayed against another.
  API keys go through `AuthService`; endpoint-scoped keys are checked against the current endpoint.
- **The caller's identity** (`sub`) is `record.user_id` for OAuth, or `api_key:{id}` for API keys, or `None` for
  `none`-auth endpoints. This `sub` drives identity forwarding, metering, per-user upstream tokens, and rate-limit
  bucketing.
- **Upstream OAuth is resolved before metering** so that a call to an unconnected upstream returns a "connect here"
  error and is never billed.
- **Connect-account tools (UPS-27, ADR-0037).** `tools/list` appends `<server>__connect_account` for each per-user
  member server the signed-in caller has not connected; `AccountConnectPrompts` decides which. A `tools/call` naming one
  is answered by `ToolsCallHandler` with the connect URL before the pipeline starts, so it is neither metered nor sent
  upstream.
- **Two response shapes.** If the client passed a `progressToken`, the response is an SSE stream of
  `notifications/progress` frames followed by the final result; otherwise it's a single buffered JSON-RPC frame. A
  modern-era call is always streamed.
- **Watchdog + cancellation.** `UpstreamCall.run` (`tool_call/upstream_call.py`) runs the call alongside `_watchdog`
  (enforcing `call_timeout` and `max_total_timeout`, with the idle window optionally reset by progress) and
  `_canceller`, which listens on a cross-replica cancel event. Cancellation → `-32800`; timeout → `-32000`.

`ToolCall.finish` is where metering settlement and the audit write happen. The audit write is fire-and-forget (§7) so it
never adds latency to the client response.

---

## 2. Bundling / composition (`application/serving/bundle_view_loader.py`)

`load_bundle_view(uow, endpoint_name, …)` turns an endpoint into a `BundleView` (`domain/bundles/bundle_view.py`) — the
in-memory picture of "what tools does this endpoint expose, under what names, with what annotations." For each tool the
order is **curation filter → profile transform → overrides**, so an explicit override wins over the profile (BND-15):

1. Resolve `Endpoint` (must be enabled) → its `Bundle`.
2. Member servers: the `BundleServer` join, keeping only `enabled` members (BND-4).
3. Curation map: the bundle's `BundleTool` rows, keyed by tool id.
4. For each `Tool` belonging to an enabled member:
   - **Disabled?** `BundleTool.enabled is False` → skip. (BND-13: a disabled tool is filtered from `tools/list` *and*
     rejected on `tools/call` — hiding alone isn't enough.)
   - **Profile:** the endpoint's profile reshapes the tool; the `write_as_read` profile sets `readOnlyHint=True` and
     `destructiveHint=False` (EP-12). The tools still perform their real upstream operations; only the *labels*
     change, which is why the profile carries an explicit warning in the UI.
   - **Overrides:** `override_name` replaces the presented name, otherwise it is `f"{server.name}__{tool.name}"` —
     `__` is the collision-free namespace separator (BND-2), which is also why server names may not contain it.
     Title and description overrides replace the tool's own; annotation overrides are merged on top of the profile's.
5. Sort by presented name → `BundleView`.

`BundleView.resolve(presented_name)` is an exact-match scan, so it matches both override names and default
`server__tool` names. `tools/list` and `tools/call` both read the same view, so what is not listed cannot be called.

---

## 3. Tool discovery (`application/discovery/discovery_service.py`)

Discovery is the **only writer of the `Tool` cache** in Postgres; `tools/list` reads exclusively from that cache
(UPS-20), so serving tools never fans out to upstreams.

- **When:** `DiscoveryService.schedule_probe(server_id)` fires a best-effort background task that never blocks the
  caller (e.g. after a server is created or updated via `ServerService`, or after an upstream OAuth connect completes).
  It is never on the request path.
- **Credentials (UPS-33):** an `upstream_oauth` server is probed with the shared connection's bearer, or any user's for
  a `per_user` server. With none the result is "upstream not connected", which does not count toward the error streak. A
  probe that changes the tool set invalidates the server's bundles, which sends `tools/list_changed` to their live
  streams.
- **How:** `discover(server_id)` opens a FastMCP client to the server, calls `list_tools()`, and reads the `initialize`
  result. Advertised capabilities are snapshotted onto `McpServer.capabilities` (UPS-22) to feed capability aggregation
  at `initialize`.
- **Change detection:** each upstream tool is hashed (`tool_schema_hash` = SHA-256 over a canonical JSON of
  name/title/description/ input_schema/annotations). A row is written only when the tool is new, its hash changed, it
  vanished or it reappeared, so an unchanged run writes no tool (UPS-18). A tool that vanishes upstream is **not
  deleted**: `stale_since` is set, the tool pipeline's stale filter stops serving it, and its curation is kept for when
  it reappears; `:refresh-tools?prune=true` deletes stale tools after a successful probe (UPS-19).
- **Health (UPS-4):** a per-server consecutive-failure counter flips `health_status` to `error` after 3 failed probes
  and self-heals to `ok` on the next success. The threshold is fixed (the `server_error_attempts` setting is not read
  yet), and the counter lives in the memory of the replica running the probes.

---

## 4. Sessions & multi-replica correctness

A session is pure data in the RESP store (`infrastructure/valkey/session_store.py`, key `bmcp:session:{id}`), so
**no request needs the replica that created it.** The record (`SessionRecord`) holds the endpoint/bundle names,
`auth_method`, `user_id`/`user_email`/`api_key_id`, the negotiated `protocol_version`, the client's `capabilities`, and
per-server `bindings`. It carries a `version` field; a version mismatch on load deletes the record and forces the client
to re-init (DEP-6). The idle TTL is a fixed 24 h; `touch` refreshes it, and pings and open GET streams count as
activity. The runtime setting `session_lifetime` is registered but not read yet, so changing it has no effect.

The split that makes multi-replica work:

- **The RESP store holds everything durable/shared** — the session record, upstream session bindings, rate counters.
- **`StreamRegistry` (`infrastructure/inprocess/stream_registry.py`) holds the only replica-local objects** — open GET
  SSE stream queues, in-flight `CallHandle`s (with their cancel event and progress queue), and pending reply futures.
- **`SignalBus` (`infrastructure/valkey/signal_bus.py`) bridges the two** over Redis pub/sub (`bmcp:signal:*`). A
  message produced on replica B for a stream owned by replica A is published to Redis; A's SignalBus delivers it to the
  local queue.

This is what lets a long-lived `GET /{endpoint}/mcp` SSE stream, and full bidirectional server→client relay
(`elicitation`, `sampling`, `roots`, `logging`), work even though the request that triggers a server→client round-trip
may land on a different replica than the one holding the stream. `ClientRelay` (`relay/client_relay.py`) implements the
round-trip: register a reply future, deliver the request over the signal bus to whichever replica owns the stream,
await the future; the client's reply comes back in through `McpGatewayRouter.post` and is routed to the waiting future
over the same bus.

---

## 5. State propagation — the invalidation bus (`infrastructure/valkey/invalidation_subscriber.py`)

Config and topology changes must reach every replica without a restart. A single Redis pub/sub channel `bmcp:invalidate`
(SES-17) carries `InvalidationEvent`s (`entity_type` ∈ server/bundle/bundle_tool/endpoint/api_key/config; `action` ∈
created/updated/deleted; `key` = natural key or uuid). Services publish an event **after they commit** a change.

Each replica runs one `InvalidationSubscriber`. On every (re)subscribe it first runs the reconnect-flush callbacks — a
subscription *gap* means it may have missed events, so it flushes caches wholesale — then dispatches each event. The
composition root (`main/composition_root.py`) registers two reactions:

- **`config`** → `RuntimeConfig.flush()`. The per-replica config cache is dropped and lazily reloaded (SES-18); config
  never propagates by TTL.
- **`bundle` / `endpoint` / `bundle_prompt` / `bundle_resource`** → `ListChangedNotifier`
  (`application/serving/list_changed_notifier.py`). Every live stream whose bundle or endpoint matches the changed key
  is sent the matching `notifications/*/list_changed` (BND-7, BND-28). Each replica walks only *its own* local streams,
  so together they cover every session with no extra coordination.

Note this `bmcp:invalidate` channel (one channel, `subscribe`) is a separate bus from the `bmcp:signal:*` family
(`psubscribe`) used for stream relay in §4.

---

## 6. Rate limiting (`infrastructure/valkey/rate_limiter.py`)

A **fixed-window counter** keyed to Redis server time so all replicas share the window (EP-17/22):
`bucket = now // window`, `INCR bmcp:rate:{scope}:{bucket}`, `EXPIRE window*2` on first hit, `allowed = count <= limit`,
`retry_after = window - (now % window)`.

- **Two scopes per endpoint**, both from `Endpoint.rate_limit`: an endpoint-wide limit (`ep:{name}:all`) and a
  per-client limit (`ep:{name}:{identity}`) where identity is `user:{id}` / `apikey:{id}` / `ip:{ip}` (EP-6).
  `initialize`/`tools/list` are exempt unless `include_initialize_list` is set (EP-19). Exceed → JSON-RPC `-32000` at
  HTTP 429 with `Retry-After`. A rate rejection is counted in-process, never an audit record. The check itself is
  `RateLimitGate` (`dispatch/rate_limit_gate.py`).
- **Fail-open by default (EP-21):** any Redis error during a check logs, bumps a counter, and *allows* the request —
  unless the endpoint opts into `fail_closed`.
- **Auth-failure lockout (EP-20):** a separate gateway-wide, IP-keyed `ValkeyAuthFailureLimiter`
  (`infrastructure/valkey/auth_failure_limiter.py`, scope `authfail:{ip}`)
  throttles credential scanning. It is invoked on any auth miss at the MCP edge and at the OAuth token endpoint, and it
  always fails open. A valid credential never touches it.

---

## 7. Cross-cutting services

- **Runtime config (`application/serving/runtime_config.py`):** the `DEFAULTS` registry
  (`domain/config/config_registry.py`) maps each key to its default and type (`call_timeout`,
  `reset_timeout_on_progress`, `max_total_timeout`, `session_lifetime`, `list_cache_ttl_ms`, `server_error_attempts`,
  `audit_retention_days`, token lifetimes). Unknown keys are rejected. Stored overrides live in `config_entries`;
  `RuntimeConfig` caches the effective values per replica and `flush`es on invalidation. `session_lifetime`,
  `server_error_attempts` and `audit_retention_days` are registered but nothing reads them yet.
- **Audit (`infrastructure/postgres/audit_writer.py`):** `QueuedAuditWriter` owns a bounded in-process queue. `record()`
  is `put_nowait` — fire-and-forget, never blocks or fails the call path; queue overflow is logged with a dropped count
  (OPS-3). A background drain
  writes one `AuditRecord` per row. Records carry endpoint/bundle/tool identity, `status` (success/error/denied),
  reason/error, duration, and caller identity — this is the metering reconciliation source (OPS-7).
- **Metering (`application/metering/metering_hook.py`):** a `MeteringHook` protocol (`pre_call` → allow/deny,
  `post_call` → settle/refund) loaded from a `"module:attr"` path or an HTTP URL
  (`infrastructure/metering/hook_loader.py`); default is a no-op. A fresh idempotency key is minted per client
  invocation and reused across internal retries (PROT-26), so a reactive OAuth retry is not double-billed. This is the
  seam an application layer hooks billing into.
- **Egress / SSRF (`infrastructure/egress/`):** enforced where each connection is dialled. `GuardedNetworkBackend`
  wraps the connection pool of every outbound client (the MCP client's and the gateway's own `httpx` clients): it
  resolves the host once, judges *all* addresses with `judge_address` (explicit allow CIDRs first, then an
  always-blocked set — link-local/metadata, loopback, the unspecified addresses — then operator deny CIDRs, with
  IPv4-mapped addresses judged as IPv4), and dials a vetted address, so a rebinding DNS answer or a followed redirect
  cannot reach a blocked address (SEC-1/2, ADR-0048). Violations raise `EgressDenied`. `check_url_allowed` still runs
  first, for an early and clearly worded refusal.
- **Per-call upstream connections (`infrastructure/fastmcp/client_factory.py`):** the client factory builds a fresh
  FastMCP `Client`
  (Streamable-HTTP only) per call, merging `{**server.static_headers, **extra_headers}` so forwarded/OAuth headers win
  over static ones. No standing upstream connections in v1 — trivially correct identity isolation (ADR-0012), at the
  cost of some latency.
- **Identity forwarding (`protocol/header_forwarding.py`, `HeaderForwarding.headers_for`):** applies the server's
  `forward_headers` client→upstream map, skipping a deny-list (`host`, `content-length`, `cookie`, `x-api-key`,
  `mcp-session-id`, any `sec-*`/`proxy-*`) — note `authorization` is *not* denied, so it can be forwarded (the seo-gsc
  introspection pattern, see the OAuth doc). A client-supplied `X-MCP-User` is stripped (only in that exact spelling
  today — see change `harden-http-edge`); the gateway injects its own `X-MCP-User: {sub}` when `send_identity_header` is
  set (AUTH-28/AUTH-29).
- **Protocol version (`protocol/protocol_version.py`):** negotiates against `SUPPORTED_PROTOCOL_VERSIONS` (newest
  first); requests older than the oldest supported fail `initialize`. `translate()` is an identity seam for future
  cross-version shimming.
- **Read-only passthrough (BND-8):** `prompts/*`, `resources/*`, and `completion/complete` fan out live to enabled
  members (no metering, no audit — they're reads). Prompt names are `server__prompt`-prefixed; resource URIs pass
  through and route by first-owner-wins.

---

## 8. How it's wired (`main/`)

`CompositionRoot` (`main/composition_root.py`) acquires the adapters in order and publishes one typed `AppContainer`
(`main/container.py`) on `app.state.container`. The MCP edge is built by `McpGatewayAssembly`
(`main/mcp_gateway_assembly.py`), which takes the session store, metering hook, audit writer, upstream client factory,
`RuntimeConfig`, stream registry, signal bus, `UpstreamTokenService` (only when encryption keys are configured), rate
limiter and auth-failure guard, and builds the `McpGatewayRouter`. Background loops started at startup: the audit
drain, the signal pub/sub loop, the invalidation subscriber, the OAuth-token purge and the periodic tool refresh.
Shutdown tears them down in order and disposes the engine and the Valkey client.

Controllers: the management controllers (upstreams, bundles, endpoints, API keys, config, audit, me, users) under
`/api/v1`; the OAuth server controllers and `McpEndpointController` at the root, so `.well-known` discovery and the
public `/{endpoint}/mcp` resolve. `/healthz` is liveness; `/readyz` checks Postgres and Valkey.

---

## File index

| File | Responsibility |
|------|----------------|
| `routing/gateway_router.py` | The Streamable-HTTP front controller: POST/GET/DELETE `/{endpoint}/mcp`, size gate, era dispatch; handlers in `dispatch/handlers/`, the call pipeline in `tool_call/` |
| `routing/admission_gate.py` | Envelope parsing and caller authentication/endpoint resolution |
| `routing/authentication/` | Endpoint authenticators: deciding who a caller is |
| `routing/adapters/` | `StatelessMcpAdapter` and `SessionMcpAdapter`: one per protocol era |
| `routing/session_stream.py` | The session-era SSE event stream |
| `protocol/` | JSON-RPC envelope, contexts, error helper, version/log/server-info, cache hints, forwarded headers, SSE framing |
| `protocol/dialect/` | One dialect per MCP revision: what differs on the wire |
| `dispatch/` | `MethodRegistry`, `MethodHandler`, rate-limit decorator and gate |
| `dispatch/handlers/` | One handler class per JSON-RPC method |
| `relay/` | `ClientRelay` and the stateless `input_required` retry machinery |
| `tool_call/` | `ToolsCallHandler`, `ToolCall` (credentials → metering → upstream → audit), `UpstreamCall` (watchdog, cancel), `ResumedCall` |
| `controllers/` | `McpEndpointController` — the FastAPI route class for `/{endpoint}/mcp` |
| `providers.py` | The FastAPI dependency that resolves the router off the container |

Outside this package, the edge relies on:

| File | Responsibility |
|------|----------------|
| `application/serving/bundle_view_loader.py` | `load_bundle_view` — what one endpoint serves (§2) |
| `application/discovery/discovery_service.py` | `DiscoveryService` — background probe, tool cache sync, capabilities, health (§3) |
| `infrastructure/fastmcp/client_factory.py` | Per-call FastMCP client, header merge, egress check |
| `api/http/client_ip.py` | Trusted-proxy client IP (`X-Forwarded-For`) |
| `infrastructure/inprocess/stream_registry.py` | `InProcessStreamRegistry` — replica-local stream queues, call handles, reply futures |
| `infrastructure/valkey/signal_bus.py` | `ValkeySignalBus` — pub/sub bridge for cross-replica delivery |
| `infrastructure/valkey/rate_limiter.py`, `auth_failure_limiter.py` | Fixed-window limits and the auth-failure lockout |
| `application/serving/runtime_config.py` | `RuntimeConfig` — runtime settings cached per replica |
| `application/metering/metering_hook.py` | The `MeteringHook` protocol — the billing seam |
| `infrastructure/inprocess/counters.py` | `InProcessCounters` — in-process metric counters (not exported yet) |
| `infrastructure/postgres/audit_writer.py` | `QueuedAuditWriter` — async, bounded, fire-and-forget audit queue |
| `infrastructure/egress/egress_policy.py` | `judge_address`, `check_url_allowed` — SSRF/egress policy |
| `infrastructure/egress/guarded_backend.py` | `GuardedNetworkBackend` — the policy enforced at connect time |
