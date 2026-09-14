# 32 — Protocol passthrough (full bidirectional proxy, every protocol era)

**Status:** Accepted · **Origin:** new (metamcp covered only fragments; scope decision: full fidelity) · **Revised:** 2026-09 for MCP 2026-07-28
**Prior art:** `../metamcp/apps/backend/src/lib/config.service.ts` (MCP_TIMEOUT / MCP_RESET_TIMEOUT_ON_PROGRESS / MCP_MAX_TOTAL_TIMEOUT), `../metamcp/apps/backend/src/lib/metamcp/metamcp-proxy.ts` (progressToken forwarding)

## Summary

bundlemcp is a **full-fidelity bidirectional MCP proxy**, not a tools-only
router. Beyond `tools/list`/`tools/call`, it relays progress, cancellation,
logging, list-changed notifications, completions — and the upstream's requests
for client input (sampling, elicitation, roots) — all working across replicas.
Motivating case: the hyperframes upstream blocks ~130 s per render;
without progress-aware timeouts and cancellation such calls are unusable
through a gateway.

MCP revision **2026-07-28** replaced the protocol's stateful core: no
`initialize` handshake, no `Mcp-Session-Id`, no HTTP GET stream, no
server-initiated requests. Its predecessors (**2025-11-25** and earlier, the
"handshake era") keep all four. The gateway therefore speaks every supported
revision on **both** hops and converts between them, so that any client era
works with any upstream era, and the newest revision both sides support is the
one used.

## Terminology

- **Handshake era** — revisions `2025-03-26`, `2025-06-18`, `2025-11-25`:
  `initialize` opens a session identified by `Mcp-Session-Id`; the client opens
  a GET stream for server→client messages; the server may send JSON-RPC
  requests to the client.
- **Modern era** — revision `2026-07-28` and later: every request carries its
  protocol version, client info and client capabilities in `params._meta`; a
  request for client input is an `InputRequiredResult` the client answers by
  retrying (Multi Round-Trip Requests, MRTR); change notifications flow on a
  `subscriptions/listen` response stream.
- **Dialect** — the gateway's implementation of one revision's wire shape on
  the client hop (PROT-13). The gateway is a *dual-era server* in the spec's
  terms: it selects the dialect from how the client opens.

## Requirements

### Progress & timeouts (all eras)

- **PROT-1** When a client's `tools/call` carries `_meta.progressToken`, the
  gateway MUST forward a progress token upstream and relay upstream
  `notifications/progress` back to the client (translating tokens/request ids
  as needed), within the same response stream serving the call.
- **PROT-2** Per-call timeout model, runtime-configurable (`Config`), matching
  metamcp's semantics: `call_timeout` (default 60 s), `reset_timeout_on_progress`
  (default true — each progress notification resets the clock),
  `max_total_timeout` (absolute cap, default 30 min). Timeout produces a
  structured MCP error to the client and a cancellation upstream (PROT-3).
- **PROT-3 Cancellation:** a cancellation MUST reach the upstream call it
  targets even when it arrives at a different replica than the one holding the
  in-flight upstream request — routed via the RESP-store pub/sub keyed by
  routing key + request id ([SES cross-replica signaling —
  30-session-management.md](30-session-management.md)). Cancellation also
  triggers the metering post-call hook with `status=error`
  ([MID-3](31-middleware.md)). The signal is `notifications/cancelled` in the
  handshake era and the client closing the response stream in the modern era
  (PROT-19); the gateway honours both in both eras.

### Server→client input in the handshake era (sampling, elicitation, roots)

- **PROT-4** *(handshake-era clients)* Upstream requests for client input —
  `sampling/createMessage`, `elicitation/create`, `roots/list` — MUST be
  relayed to the downstream client as JSON-RPC requests on its GET stream and
  the client's response routed back to the requesting upstream, including
  across replicas (the client's event stream may be pinned to a different
  replica than the upstream connection; delivery goes through the same pub/sub
  routing as PROT-3). Whether the upstream itself asked with a server-initiated
  request (handshake upstream) or with an `InputRequiredResult` (modern
  upstream, PROT-21) is invisible to the client.
- **PROT-5** Capability-gated: an upstream request type is relayed only if the
  downstream client advertised the corresponding capability — at `initialize`
  for handshake clients, in `_meta` on the request for modern clients;
  otherwise the gateway answers the upstream with a method-not-supported
  error itself. The capability set offered TO each upstream MUST therefore be
  the intersection of what the client offered and what the gateway can relay.
- **PROT-6** Relayed requests for client input inherit the pending call's
  timeout budget (PROT-2); an unanswered elicitation/sampling request times
  out with the call. In the modern era the same budget bounds how long a parked
  call waits for the client's retry (PROT-18).

### Notifications & misc

- **PROT-7** Upstream `notifications/message` (logging) are relayed to the
  client when it asked for them: a handshake client enables logging with
  `logging/setLevel`, which is stored on its session and fanned out to member
  upstreams that support logging; a modern client sets
  `_meta["io.modelcontextprotocol/logLevel"]` per request (PROT-20). Log
  messages are always delivered on the stream of the request they relate to,
  never on a notification stream.
- **PROT-8** *(handshake era)* `ping` is answered by the gateway in both
  directions; a client ping counts as session activity and refreshes the SES-1
  TTL. `ping` is not a modern-era method and is answered with method-not-found
  there.
- **PROT-9** `completion/complete` (prompt/resource-template argument
  completion) is routed to the owning upstream using the same prefix rules as
  tools ([BND-3](12-bundles.md)).
- **PROT-10** Upstream `notifications/*/list_changed` (tools, prompts,
  resources) trigger re-discovery ([DISC-1](11-tool-discovery.md)) and are
  propagated to connected clients per [BND-7](12-bundles.md): on the GET
  stream for handshake clients, on the `subscriptions/listen` stream for modern
  clients (PROT-17).

### Capability & version aggregation

- **PROT-11** The bundle's capability advertisement (the `initialize` result
  for handshake clients, the `server/discover` result for modern clients)
  declares a capability iff at least one enabled member server supports it. The
  set is computed from the per-server `capabilities` snapshot captured at
  discovery ([DISC-6](11-tool-discovery.md)): `tools` (always — the gateway
  supports tools even with zero members), `prompts`, `resources`,
  `completions`, and `logging`. `listChanged: true` is advertised where the
  gateway can emit it (tools always; prompts/resources when ≥1 member
  advertises it); `resources.subscribe: true` when ≥1 member supports it.
  `extensions` is advertised only for extensions the gateway itself proxies
  (none in v1; the Tasks extension is the first candidate).
- **PROT-12** *(handshake era)* Protocol version: the gateway negotiates the
  highest handshake-era version common with the client at its `initialize`; a
  client requesting a version older than the supported window fails
  `initialize` with an error that names the supported versions. Negotiation
  with each upstream is independent (PROT-21).

### The modern era on the client hop

- **PROT-13 Dialects and era detection.** The edge holds a registry of
  *dialects*, one per supported revision, and picks the dialect once per
  request from how the client opens: a request carrying
  `_meta["io.modelcontextprotocol/protocolVersion"]` is served by that
  revision's modern dialect, statelessly; an `initialize` request negotiates a
  handshake dialect (PROT-12) that is then recorded on the session; a request
  carrying `Mcp-Session-Id` is served by its session's dialect. A request that
  is none of these is rejected with `-32602` and HTTP 400, the message naming
  the missing `_meta` fields and the supported versions, so a dual-era client
  falls back to `initialize` and an operator sees why. A modern request naming
  a version the registry does not hold is rejected with `-32022`
  (`UnsupportedProtocolVersion`), HTTP 400, and `data.supported` listing the
  modern versions. Adding a revision means adding one dialect and registering
  it; no handler changes (PROT-22). Handshake dialects can be switched off by
  configuration (`legacy_protocol_enabled`) once the deprecation window closes.
- **PROT-14 `server/discover`.** MUST be served for every modern dialect,
  without fanning out to members: `supportedVersions` (the modern dialects),
  `capabilities` (PROT-11), `instructions` (the bundle description), the
  gateway's server info in `_meta`, and cache hints (PROT-16). Rate limiting
  treats it like `initialize` ([RATE-4](16-rate-limiting.md)).
- **PROT-15 Mirrored headers.** For modern requests the edge MUST validate
  `MCP-Protocol-Version` against `_meta`, `Mcp-Method` against `method`,
  `Mcp-Name` against `params.name`/`params.uri` (decoding the `=?base64?…?=`
  sentinel), and every `Mcp-Param-*` header against the argument the
  presented tool's `x-mcp-header` annotations designate; a mismatch or a
  missing required header is HTTP 400 with `-32020` (`HeaderMismatch`). Headers
  on handshake-era requests are not trusted for policy. `x-mcp-header`
  annotations in upstream tool schemas pass through `tools/list` unchanged.
- **PROT-16 Result shaping and cache hints.** Every modern result carries
  `resultType` (`"complete"`, or `"input_required"` per PROT-18) and the
  gateway's server info in `_meta`. `tools/list`, `prompts/list`,
  `resources/list`, `resources/templates/list`, `resources/read` and
  `server/discover` carry `ttlMs` and `cacheScope`: list results are
  `public` with a runtime-configurable TTL (`list_cache_ttl_ms`, default
  5 min), invalidated by `listChanged`; `resources/read` forwards the
  upstream's hint when it gave one and is otherwise `ttlMs: 0`, `private`.
  Error codes follow the modern table: resource-not-found is `-32602` (it is
  `-32002` for handshake clients, and a modern upstream's `-32602` is mapped
  back for them). `tools/list` order is deterministic (sorted by presented
  name). Handshake-era results are byte-for-byte what they were before this
  revision.
- **PROT-17 `subscriptions/listen`.** A modern client opens change
  notifications with one long-lived POST whose response stream first carries
  `notifications/subscriptions/acknowledged` echoing the subset of the filter
  the gateway honours, then only the notification types acknowledged, each
  tagged with `_meta["io.modelcontextprotocol/subscriptionId"]` = the request
  id. The gateway honours `toolsListChanged` (BND-7 invalidations, delivered
  cross-replica like PROT-10). `promptsListChanged`, `resourcesListChanged` and
  `resourceSubscriptions` depend on a standing upstream connection
  ([ADR-0012](../docs/adr/0012-per-call-upstream-connections.md)) and are
  omitted from the acknowledgement until pooling lands. The stream sends SSE
  keep-alive comments, ends with a completion result on graceful shutdown, and
  is closed by the client to unsubscribe. GET and DELETE on the endpoint
  without an `Mcp-Session-Id` answer 405 ([EP-1](14-endpoints.md)).
- **PROT-18 Multi Round-Trip Requests.** When an upstream needs client input
  during `tools/call`, `prompts/get` or `resources/read` for a modern client,
  the gateway answers `resultType: "input_required"` with `inputRequests` and
  a sealed `requestState`; the client retries the same method with
  `inputResponses` and the state, and any replica MUST be able to serve the
  retry. Two strategies, chosen per upstream era:
  - **Pass-through** (modern upstream): the upstream's own
    `InputRequiredResult` is forwarded — `inputRequests` verbatim, its
    `requestState` sealed inside the gateway's — and the retry re-issues the
    call upstream with the client's `inputResponses` and the upstream's state.
    No gateway state exists between the two requests.
  - **Park and resume** (handshake upstream): the upstream's server-initiated
    request is turned into `inputRequests`; the in-flight upstream call stays
    parked on its reply future, bounded by PROT-6; the retry routes the
    answer to the parking replica over the signal bus and the result back to
    the replica serving the retry. If no replica claims the retry (the parking
    replica is gone), the call is **re-run** with the requests answered from
    `inputResponses` as they recur, so the client still gets a result; this
    fallback may repeat the upstream's side effects before the elicitation and
    is logged as such.
  `requestState` is integrity-protected with the gateway's token cipher and
  binds the principal, the presented tool and argument digest, the metering
  idempotency key and an expiry; a state that fails verification, belongs to
  another caller or has expired is rejected with `-32602`. Metering fires
  `pre_call` once per client invocation ([MID-3](31-middleware.md)): a resumed
  call is not re-metered; a re-run reuses the idempotency key. Only requests the
  client declared support for in `_meta` capabilities are placed in
  `inputRequests` (PROT-5). Without token encryption keys the bridge is
  unavailable and reports so with a structured error rather than sealing
  plaintext. *Residual:* both strategies are implemented for `tools/call`;
  on `prompts/get` and `resources/read` a modern client is not yet bridged
  (a handshake upstream's request fails fast, a modern upstream's
  `input_required` is reported as an error), while a handshake client is
  relayed on every method.
- **PROT-19 Cancellation by disconnect.** Modern `tools/call` responses are
  always streamed (`text/event-stream`, progress optional), so the client
  closing the stream is an unambiguous cancellation that the gateway applies
  to the upstream call. `notifications/cancelled` is still accepted with 202 in
  both eras.
- **PROT-20 Per-request log level.** A modern request's
  `_meta["io.modelcontextprotocol/logLevel"]` enables `notifications/message`
  at or above that level on that request's response stream only; requests
  without it receive none. `logging/setLevel` is not a modern-era method.

### The upstream hop

- **PROT-21 Per-upstream era.** The gateway's upstream client negotiates per
  server: `server/discover` first, falling back to `initialize` when the
  upstream is handshake-era, unless the server's `protocol_mode`
  ([SRV-10](10-server-registry.md)) pins it. The negotiated version is recorded
  at discovery. A handshake upstream's server-initiated requests and a modern
  upstream's `input_required` results reach the gateway through one callback
  shape, so both convert to either client era (PROT-4, PROT-18). Results of
  either era are normalised into the gateway's internal model before a dialect
  shapes them for the client (PROT-16).
- **PROT-22 Adding a protocol revision.** A new revision is supported by
  adding one dialect class (client hop) and, if the upstream SDK does not
  absorb it, one adapter (upstream hop), registering the version, running the
  MCP conformance suite for that revision against the compose stack, and
  recording an ADR. Handlers, the relay, metering and audit MUST NOT need to
  change for a revision that keeps the method set. The revision lists and the
  per-revision method sets are read from the MCP SDK's registry
  (`mcp_types.version`, `mcp_types.methods`); the gateway keeps only its own
  decisions, such as the floor of the handshake window.

## Implementation

**Implemented** ([ADR-0021](../docs/adr/0021-mcp-surface-completion.md)):
prompts/resources/completions routing (PROT-9), capability aggregation
(PROT-11), handshake version negotiation (PROT-12), and the roots/logging
relay (PROT-4/PROT-7) on the request/response path and within an active call.
**Implemented** ([ADR-0029](../docs/adr/0029-dialects-and-dual-era-edge.md),
[ADR-0030](../docs/adr/0030-fastmcp-4.md)): PROT-13 to PROT-22, with the
PROT-17 (only `toolsListChanged` acknowledged) and PROT-18 (`tools/call` only
for modern clients) residuals noted in place.
**Pooling-dependent residual:** any upstream→client *push* that must arrive
between calls — `notifications/resources/updated`, PROT-7 upstream
`notifications/message`, and PROT-10 upstream `*/list_changed` **outside an
active call** — requires a persistent upstream connection, which the
per-call-connection model (ADR-0012) does not provide. These capabilities are
delivered *within* an active call window; full between-call push lands with
connection pooling ([SES-8](30-session-management.md), ADR-0012).

## Out of scope

- Persisting/replaying server→client requests across a *client* disconnect —
  if the client's stream is gone, pending upstream requests fail fast (a parked
  modern call waits only for its PROT-6 budget).
- Rate-limiting relayed notifications (revisit if an upstream floods).
- Proxying protocol extensions (Tasks, MCP Apps) — advertised as unsupported
  (PROT-11) until a dedicated spec covers them.

## Open questions

- ~~How much of PROT-4's relay FastMCP v3 provides natively? What is the
  cross-replica correlation design?~~ **Resolved**
  ([ADR-0016](../docs/adr/0016-relay-design.md)): the downstream half is built
  on bundlemcp's own endpoint edge (SSE call responses + GET event stream);
  the upstream half uses FastMCP's client `progress_handler` /
  `elicitation_handler` / `sampling_handler`. Cross-replica routing is a
  publish-only RESP `bmcp:signal:*` bus feeding per-replica registries of
  streams/calls/reply-futures (`gateway/signals/`, `gateway/streams/`).
- ~~Can a modern upstream's `input_required` be forwarded without gateway
  state?~~ **Resolved** (ADR-0030 spike): the SDK exposes the raw
  `InputRequiredResult` and accepts `inputResponses`/`requestState` on the
  retry, so PROT-18 pass-through is native.
