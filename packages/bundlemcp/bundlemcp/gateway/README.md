# gateway — the MCP serving edge

This package is the core of bundlemcp: it terminates the client-facing
Streamable-HTTP MCP protocol, composes a bundle's tool surface, proxies calls to
the right upstream server, and records what happened. The client edge is
**hand-rolled** (`mcp_endpoint.py`) rather than delegated to FastMCP's session
manager, precisely so that session state lives in the RESP store and any replica
can serve any request (ARC-9/ARC-10). FastMCP is used only for the *upstream*
leg.

Read [../oauth/README.md](../oauth/README.md) for how callers are
authenticated; this doc picks up once a request is authorized.

> **"the RESP store" = Valkey.** The live-state store ships as Valkey (BSD-3),
> a drop-in RESP server; the client is `redis-py` and the URL scheme stays
> `redis://`, so `redis`-named symbols, `bmcp:` keys, and "Redis pub/sub /
> server time" below refer to the RESP protocol the code speaks — see
> [../../README.md](../../README.md#a-note-on-the-resp-store-valkey-not-redis-adr-0022)
> and ADR-0022.

---

## 1. The request lifecycle

A `tools/call` to `POST /{endpoint_name}/mcp` (`mcp_endpoint.py::mcp_post`)
travels through these stages. Each is a named function you can grep for.

```
HTTP POST /{endpoint}/mcp
  │
  ├─ load_bundle_view(db, endpoint)         composition.py — 404 if missing/disabled
  ├─ _authenticate(request, db, view)       oauth bearer OR api key OR none
  │     └─ miss → note_auth_failure → 401 + WWW-Authenticate (RFC 9728) or 429
  ├─ parse JSON-RPC body, dispatch on method
  ├─ sessions.load(mcp-session-id)          Redis — 404 if missing/endpoint mismatch
  ├─ sessions.touch(session_id)             refresh idle TTL
  ├─ _enforce_rate_limit(…)                 429 short-circuit (§6)
  └─ _handle_call(runtime, request, view, record, body)
        ├─ view.resolve(presented_name)     composition — unknown/disabled → DENIED + error
        ├─ (upstream OAuth?) ensure_access_token   BEFORE metering, so unconnected ≠ debited
        ├─ metering.pre_call(ctx)           deny → DENIED + error
        ├─ _forward_headers(request, server, sub)   then merge upstream bearer
        ├─ _drive_upstream(…)               per-call FastMCP client → call_tool_mcp
        │     └─ reactive OAuth retry once on upstream 401 (UPO-4)
        └─ finalize → metering.post_call + audit.record → JSON-RPC result/error
```

Key points that are easy to miss:

- **`initialize` never touches upstreams.** It negotiates the protocol version
  (`protocol_version.py`), mints a session id, and returns aggregated
  capabilities from the cached per-server `capabilities` snapshot (PROT-11). The
  session record is written to Redis here and the id is returned in the
  `Mcp-Session-Id` response header.
- **Auth precedence is OAuth then API key.** OAuth validation is a direct DB
  lookup on `OAuthAccessToken.access_token_hash`, checking `revoked`, expiry, and
  **audience** (`row.endpoint_id == view.endpoint.id`, EP-3a) — a token minted
  for one endpoint cannot be replayed against another. API keys go through
  `AuthService`; endpoint-scoped keys are checked against the current endpoint.
- **The caller's identity** (`sub`) is `record.user_id` for OAuth, or
  `api_key:{id}` for API keys, or `None` for `none`-auth endpoints. This `sub`
  drives identity forwarding, metering, per-user upstream tokens, and rate-limit
  bucketing.
- **Upstream OAuth is resolved before metering** so that a call to an
  unconnected upstream returns a "connect here" error and is never billed.
- **Two response shapes.** If the client passed a `progressToken`, the response
  is an SSE stream of `notifications/progress` frames followed by the final
  result; otherwise it's a single buffered JSON-RPC frame.
- **Watchdog + cancellation.** `_drive_upstream` runs the call alongside a
  watchdog (enforcing `call_timeout`, `max_total_timeout`, with the idle window
  optionally reset by progress) and a canceller that listens on a cross-replica
  cancel event. Cancellation → `-32800`; timeout → `-32000`.

`finalize` is where metering settlement and the audit write happen. The audit
write is fire-and-forget (§7) so it never adds latency to the client response.

---

## 2. Bundling / composition (`composition.py`)

`load_bundle_view(db, endpoint_name)` turns an endpoint into a `BundleView` — the
in-memory picture of "what tools does this endpoint expose, under what names,
with what annotations." The pipeline is **curation filter → overrides → profile
transform**:

1. Resolve `Endpoint` (must be enabled) → its `Bundle`.
2. Member servers: the `BundleServer` join, keeping only `enabled` members
   (BND-4).
3. Curation map: the bundle's `BundleTool` rows, keyed by tool id.
4. For each `Tool` belonging to an enabled member:
   - **Disabled?** `BundleTool.enabled is False` → skip. (TM-2: a disabled tool
     is filtered from `tools/list` *and* rejected on `tools/call` — hiding alone
     isn't enough.)
   - **Presented name:** `override_name` if set, otherwise
     `f"{server.name}__{tool.name}"`. `PREFIX_SEP = "__"` is the collision-free
     namespace separator (BND-2), which is also why server names may not contain
     `__`.
   - **Annotations:** apply the profile transform, then merge per-tool
     annotation overrides on top (explicit overrides win, TM-4).
   - **title / description:** per-bundle overrides else the tool's own.
5. Sort by presented name → `BundleView`.

`BundleView.resolve(presented_name)` is an exact-match scan, so it matches both
override names and default `server__tool` names.

**ChatGPT profile re-annotation (PROF-3):** `_apply_profile_annotations` — when
the endpoint's profile is `chatgpt`, it merges `readOnlyHint=True` and
`destructiveHint=False` onto a copy of each tool's annotations. The tools still
perform their real upstream operations; only the *labels* change, which is why
the profile carries an explicit warning in the UI.

---

## 3. Tool discovery (`discovery.py`)

Discovery is the **only writer of the `Tool` cache** in Postgres; `tools/list`
reads exclusively from that cache (DISC-4), so serving tools never fans out to
upstreams.

- **When:** `DiscoveryService.schedule_probe(server_id)` fires a best-effort
  background task that never blocks the caller (e.g. after a server is created
  or updated via `ServerService`). It is never on the request path.
- **How:** `discover(server_id)` opens a FastMCP client to the server,
  calls `list_tools()`, and reads the `initialize` result. Advertised
  capabilities are snapshotted onto `McpServer.capabilities` (DISC-6) to feed
  capability aggregation at `initialize`.
- **Change detection:** each upstream tool is hashed
  (`tool_schema_hash` = SHA-256 over a canonical JSON of name/title/description/
  input_schema/annotations). A row is rewritten only when its hash changed
  (DISC-2); `last_seen_at` is always bumped. Tools that vanish upstream are
  **not deleted** — they keep their old `last_seen_at` (DISC-3).
- **Health (SRV-4):** a per-server consecutive-failure counter flips
  `health_status` to `error` after N attempts (default 3) and self-heals to
  `ok` on the next success.

---

## 4. Sessions & multi-replica correctness

A session is pure data in the RESP store (`store/sessions.py`, key
`bmcp:session:{id}`), so **no request needs the replica that created it.** The
record (`SessionRecord`) holds the endpoint/bundle names, `auth_method`,
`user_id`/`user_email`/`api_key_id`, the negotiated `protocol_version`, the
client's `capabilities`, and per-server `bindings`. It carries a `version` field;
a version mismatch on load deletes the record and forces the client to re-init
(DEP-6). Idle TTL defaults to 24h (`session_lifetime`, `0` = no expiry);
`touch` refreshes it, and pings/open GET streams count as activity.

The split that makes multi-replica work:

- **The RESP store holds everything durable/shared** — the session record,
  upstream session bindings, rate counters.
- **`StreamRegistry` (`streams.py`) holds the only replica-local objects** —
  open GET SSE stream queues, in-flight `CallHandle`s (with their cancel event
  and progress queue), and pending reply futures.
- **`SignalBus` (`signals.py`) bridges the two** over Redis pub/sub
  (`bmcp:signal:*`). A message produced on replica B for a stream owned by
  replica A is published to Redis; A's SignalBus delivers it to the local queue.

This is what lets a long-lived `GET /{endpoint}/mcp` SSE stream, and full
bidirectional server→client relay (`elicitation`, `sampling`, `roots`,
`logging`), work even though the request that triggers a server→client
round-trip may land on a different replica than the one holding the stream.
`_build_relay_handlers` implements the round-trip: register a reply future,
`signals.deliver(...)` the request to whichever replica owns the stream, await
the future; the client's reply comes back in through `mcp_post` and is routed to
the waiting future via `signals.reply`.

---

## 5. State propagation — the invalidation bus (`store/invalidation.py`)

Config and topology changes must reach every replica without a restart. A single
Redis pub/sub channel `bmcp:invalidate` (STP-1) carries `InvalidationEvent`s
(`entity_type` ∈ server/bundle/bundle_tool/endpoint/api_key/config; `action` ∈
created/updated/deleted; `key` = natural key or uuid). Services publish an event
**after they commit** a change.

Each replica runs one `InvalidationSubscriber`. On every (re)subscribe it first
runs the reconnect-flush callbacks — a subscription *gap* means it may have
missed events, so it flushes caches wholesale — then dispatches each event. The
wiring in `app.py::_on_invalidation` reacts to two entity types:

- **`config`** → `RuntimeConfig.flush()`. The per-replica config cache is
  dropped and lazily reloaded (STP-2); config never propagates by TTL.
- **`bundle` / `endpoint`** → BND-7 `list_changed`. Every live session whose
  `bundle_name`/`endpoint_name` matches the changed key is sent
  `notifications/tools/list_changed`. Each replica walks only *its own* local
  streams, so together they cover every session with no extra coordination.

Note this `bmcp:invalidate` channel (one channel, `subscribe`) is a separate bus
from the `bmcp:signal:*` family (`psubscribe`) used for stream relay in §4.

---

## 6. Rate limiting (`ratelimit.py`)

A **fixed-window counter** keyed to Redis server time so all replicas share the
window (RATE-2/7): `bucket = now // window`, `INCR bmcp:rate:{scope}:{bucket}`,
`EXPIRE window*2` on first hit, `allowed = count <= limit`,
`retry_after = window - (now % window)`.

- **Two scopes per endpoint**, both from `Endpoint.rate_limit`: an
  endpoint-wide limit (`ep:{name}:all`) and a per-client limit
  (`ep:{name}:{identity}`) where identity is `user:{id}` / `apikey:{id}` /
  `ip:{ip}` (EP-6). `initialize`/`tools/list` are exempt unless
  `include_initialize_list` is set (RATE-4). Exceed → JSON-RPC `-32000` at HTTP
  429 with `Retry-After`. A rate rejection is a metric, never an audit record.
- **Fail-open by default (RATE-6):** any Redis error during a check logs, bumps a
  counter, and *allows* the request — unless the endpoint opts into
  `fail_closed`.
- **Auth-failure lockout (RATE-5):** a separate gateway-wide, IP-keyed
  `AuthFailureLimiter` (scope `authfail:{ip}`) throttles credential scanning. It
  is invoked on any auth miss at the MCP edge and at the OAuth token endpoint,
  and it always fails open. A valid credential never touches it.

---

## 7. Cross-cutting services

- **Runtime config (`runtime_config.py`):** a `DEFAULTS` registry of
  `key → (default, type)` (`call_timeout`, `reset_timeout_on_progress`,
  `max_total_timeout`, `session_lifetime`, `server_error_attempts`,
  `audit_retention_days`). `coerce` type-validates and rejects unknown keys.
  Stored overrides live in `config_entries`; `RuntimeConfig` caches the effective
  values per replica and `flush`es on invalidation.
- **Audit (`audit.py`):** `AuditWriter` owns a bounded in-process queue.
  `record()` is `put_nowait` — fire-and-forget, never blocks or fails the call
  path; queue overflow is a metric + log, not silent loss (AUD-3). A background
  drain writes one `AuditRecord` per row. Records carry endpoint/bundle/tool
  identity, `status` (success/error/denied), reason/error, duration, and caller
  identity — this is the metering reconciliation source (AUD-7).
- **Metering (`metering.py`):** a `MeteringHook` protocol (`pre_call` →
  allow/deny, `post_call` → settle/refund) loaded from a `"module:attr"` path;
  default is a no-op. A fresh idempotency key is minted per client invocation and
  reused across internal retries (MID-3), so a reactive OAuth retry is not
  double-billed. This is the seam an application layer (ultra-mcp) hooks billing
  into.
- **Egress / SSRF (`egress.py`):** `check_url_allowed` runs before every upstream
  connection. It resolves *all* addresses for the host (so a hostname can't
  smuggle a blocked IP) and evaluates: explicit allow CIDRs first, then an
  always-blocked set (link-local/metadata `169.254.0.0/16`, IPv6 link-local,
  loopback), then operator deny CIDRs (SEC-1/2). Violations raise `EgressDenied`.
- **Per-call upstream connections (`upstream.py`):** `default_client_factory`
  builds a fresh FastMCP `Client` (Streamable-HTTP only) per call, merging
  `{**server.static_headers, **extra_headers}` so forwarded/OAuth headers win
  over static ones. No standing upstream connections in v1 — trivially correct
  identity isolation (ADR-0012), at the cost of some latency.
- **Identity forwarding (`_forward_headers`):** applies the server's
  `forward_headers` client→upstream map, skipping a deny-list (`host`,
  `content-length`, `cookie`, `x-api-key`, `mcp-session-id`, any `sec-*`/`proxy-*`)
  — note `authorization` is *not* denied, so it can be forwarded (the seo-gsc
  introspection pattern, see the OAuth doc). Any client-supplied `X-MCP-User` is
  always stripped; the gateway injects its own `X-MCP-User: {sub}` when
  `send_identity_header` is set (FWD-2/FWD-3).
- **Protocol version (`protocol_version.py`):** negotiates against
  `SUPPORTED_PROTOCOL_VERSIONS` (newest first); requests older than the oldest
  supported fail `initialize`. `translate()` is an identity seam for future
  cross-version shimming.
- **Read-only passthrough (BND-8):** `prompts/*`, `resources/*`, and
  `completion/complete` fan out live to enabled members (no metering, no audit —
  they're reads). Prompt names are `server__prompt`-prefixed; resource URIs pass
  through and route by first-owner-wins.

---

## 8. How it's wired (`../api/app.py` lifespan)

`create_app`'s lifespan constructs the object graph and attaches it to
`app.state`. The centerpiece is `app.state.gateway = GatewayRuntime(...)`, which
bundles the `SessionStore`, metering hook, `AuditWriter`, upstream client
factory, `RuntimeConfig`, `StreamRegistry`, `SignalBus`, `UpstreamTokenStore`
(only if encryption keys are configured), `RateLimiter`, and
`AuthFailureLimiter`. Background loops started here: the audit drain, the signal
pub/sub loop, the invalidation subscriber, and a periodic OAuth-token purge.
Shutdown tears them down in order and disposes the engine and Redis client.

Routers: management routers (`servers`, `bundles`, `endpoints`, `api_keys`,
`config`, `audit`, `me`, `users`) under `/api/v1`; the OAuth server routers and
`mcp_endpoint` at root (so `.well-known` discovery and public `/{endpoint}/mcp`
resolve). `/healthz` is liveness; `/readyz` checks Postgres and Redis.

---

## File index

| File | Responsibility |
|------|----------------|
| `mcp_endpoint.py` | The Streamable-HTTP edge: POST/GET/DELETE `/{endpoint}/mcp`, `GatewayRuntime`, auth, session lifecycle, call handling, relay, forwarding |
| `composition.py` | `BundleView`, `load_bundle_view`, name prefixing, override/curation resolution, profile transforms |
| `discovery.py` | `DiscoveryService` — background probe, tool cache sync, schema hashing, capabilities, health |
| `upstream.py` | `default_client_factory` — per-call FastMCP client, header merge, egress check |
| `proxy.py` | Trusted-proxy `client_ip` resolution (X-Forwarded-For handling) |
| `streams.py` | `StreamRegistry` — replica-local stream queues, call handles, reply futures |
| `signals.py` | `SignalBus` — Redis pub/sub bridge for cross-replica delivery |
| `ratelimit.py` | `RateLimiter`, `AuthFailureLimiter` — fixed-window limits |
| `runtime_config.py` | `RuntimeConfig`, `DEFAULTS`, `coerce` — durable runtime settings |
| `metering.py` | `MeteringHook` protocol + loader — the billing seam |
| `metrics.py` | `Counters` — in-process metric counters |
| `audit.py` | `AuditWriter` — async, bounded, fire-and-forget audit queue |
| `egress.py` | `check_url_allowed` — SSRF/egress policy |
| `protocol_version.py` | MCP protocol-version negotiation |
