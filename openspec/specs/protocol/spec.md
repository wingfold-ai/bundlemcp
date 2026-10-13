# protocol Specification

## Purpose

The MCP surface the gateway speaks to clients and upstreams. bundlemcp is a bidirectional proxy, not a tools-only
router: it relays progress, cancellation, logging, completions, list-changed notifications and the upstream's requests
for client input, across protocol revisions (the session-based handshake era and the stateless 2026-07-28 era) with one
dialect per revision. Every tool call runs through a fixed pipeline (curation, profile, metering, audit), and the
metering hook is the supported, versioned extension point where an application layer plugs in billing.

Session storage and cross-replica delivery are the sessions slice; what is recorded per call is the operations slice.

It merges what were separate specs until 2026-10-13: Protocol passthrough, Tool-call pipeline and metering hook.

## Terminology

- **Handshake era** — revisions `2025-03-26`, `2025-06-18`, `2025-11-25`: `initialize` opens a session identified by
  `Mcp-Session-Id`; the client opens a GET stream for server→client messages; the server may send JSON-RPC requests to
  the client.
- **Modern era** — revision `2026-07-28` and later: every request carries its protocol version, client info and client
  capabilities in `params._meta`; a request for client input is an `InputRequiredResult` the client answers by retrying
  (Multi Round-Trip Requests, MRTR); change notifications flow on a `subscriptions/listen` response stream.
- **Dialect** — the gateway's implementation of one revision's wire shape on the client hop (PROT-13). The gateway is a
  *dual-era server* in the spec's terms: it selects the dialect from how the client opens.

## Requirements

### Requirement: PROT-1 Progress relay
When a client's `tools/call` carries `_meta.progressToken`, the gateway MUST forward a progress token upstream and relay
upstream `notifications/progress` back to the client (translating tokens/request ids as needed), within the same
response stream serving the call.

#### Scenario: Progress streamed before the result
- **WHEN** a client calls a tool with `_meta.progressToken` and the upstream emits 30 progress notifications
- **THEN** the response is `text/event-stream` carrying 30 `notifications/progress` events with the client's token,
  then the final result

#### Scenario: No progress token
- **WHEN** a handshake-era client calls a tool without a progress token
- **THEN** the response is a single buffered JSON-RPC message

### Requirement: PROT-2 Per-call timeout model
Per-call timeouts SHALL be runtime-configurable (`Config`), matching metamcp's semantics: `call_timeout` (default 60 s),
`reset_timeout_on_progress` (default true — each progress notification resets the clock), `max_total_timeout`
(absolute cap, default 30 min). A timeout produces a structured MCP error to the client and ends the upstream call.

#### Scenario: Silent call times out
- **WHEN** `call_timeout` is short and the upstream sends nothing for longer than it
- **THEN** the client receives a JSON-RPC error naming `call_timeout`

#### Scenario: Progress keeps the call alive
- **WHEN** the upstream keeps emitting progress past `call_timeout` with reset-on-progress enabled
- **THEN** the call completes with its result instead of timing out

### Requirement: PROT-3 Cancellation
A cancellation MUST reach the upstream call it targets even when it arrives at a different replica than the one
holding the in-flight upstream request — routed via the RESP-store pub/sub keyed by routing key + request id
([SES-13](../sessions/spec.md)). A cancelled call SHALL be reported to the metering post-call hook with
outcome `cancelled` ([PROT-26](../protocol/spec.md)). The signal is `notifications/cancelled` naming the request id on
the same session in the handshake era, and the client closing the call's response stream in the modern era (PROT-19)
and for a handshake-era call streamed with a progress token.

#### Scenario: notifications/cancelled aborts the call
- **WHEN** a handshake-era client sends `notifications/cancelled` for request 7 while that `tools/call` is in flight
- **THEN** the call ends with a JSON-RPC error `cancelled` and the hook's `post_call` receives outcome `cancelled`

#### Scenario: Cancellation from another replica
- **WHEN** the call runs on replica A and the cancellation arrives at replica B
- **THEN** A receives the cancel signal over the store and ends the upstream call

### Requirement: PROT-4 Server→client input relay for handshake-era clients
*(handshake-era clients)* Upstream requests for client input — `sampling/createMessage`, `elicitation/create`,
`roots/list` — made during a request the client sent MUST be relayed to the downstream client as JSON-RPC requests on
its GET stream and the client's response routed back to the requesting upstream, including across replicas (the
client's event stream may be pinned to a different replica than the upstream connection; delivery goes through the
same pub/sub routing as PROT-3). This holds for `tools/call` and for the read-only passthrough methods. Whether the
upstream itself asked with a server-initiated request (handshake upstream) or with an `InputRequiredResult` (modern
upstream, PROT-21) is invisible to the client.

#### Scenario: Elicitation relayed on the GET stream
- **WHEN** a handshake client that advertised `elicitation` holds a GET stream and calls a tool whose upstream asks for
  input
- **THEN** an `elicitation/create` request arrives on the GET stream, and the client's POSTed reply completes the call

#### Scenario: Modern upstream, handshake client
- **WHEN** a modern-era upstream answers `input_required` for a handshake client's call
- **THEN** the client sees an ordinary `elicitation/create` request on its GET stream

#### Scenario: Roots
- **WHEN** an upstream asks `roots/list` during a call of a client that advertised `roots`
- **THEN** the client's roots are returned to the upstream

### Requirement: PROT-5 Capability-gated relay
Relay SHALL be capability-gated: an upstream request type is relayed only if the downstream client advertised the
corresponding capability — at `initialize` for handshake clients, in `_meta` on the request for modern clients;
otherwise the gateway answers the upstream with a method-not-supported error itself. The capability set offered TO each
upstream MUST therefore be the intersection of what the client offered and what the gateway can relay.

#### Scenario: Elicitation not advertised
- **WHEN** a client that did not advertise `elicitation` calls a tool whose upstream asks for input
- **THEN** nothing is sent to the client and the upstream's request fails, which surfaces in the call's result

### Requirement: PROT-6 Relay inherits the call budget
Relayed requests for client input SHALL inherit the pending call's timeout budget (PROT-2); an unanswered
elicitation/sampling request times out with the call. In the modern era the same budget bounds how long a parked call
waits for the client's retry (PROT-18).

#### Scenario: Unanswered elicitation
- **WHEN** the client never answers a relayed `elicitation/create`
- **THEN** the call ends with the PROT-2 timeout error

### Requirement: PROT-7 Logging relay
Upstream `notifications/message` (logging) SHALL be relayed to the client when it asked for them, at or above the level
it asked for: a handshake client enables logging with `logging/setLevel`, which is stored on its session and applied to
every later upstream request on that session; a modern client sets `_meta["io.modelcontextprotocol/logLevel"]` per
request (PROT-20). For a handshake client a log message is delivered on the call's response stream when the call is
streamed, otherwise on its GET stream.

#### Scenario: Handshake client after setLevel
- **WHEN** a handshake client sends `logging/setLevel` `info`, holds a GET stream and calls a tool that logs at `info`
- **THEN** a `notifications/message` with the upstream's log arrives on the GET stream

#### Scenario: Unknown level
- **WHEN** a client sends `logging/setLevel` with level `loud`
- **THEN** the gateway answers `-32602`

### Requirement: PROT-8 Ping
*(handshake era)* `ping` SHALL be answered by the gateway in both directions; a client ping counts as session activity
and refreshes the SES-1 TTL. `ping` is not a modern-era method and is answered with method-not-found there.

#### Scenario: Handshake ping
- **WHEN** a handshake client sends `ping` on its session
- **THEN** the gateway answers an empty result and refreshes the session TTL

#### Scenario: Modern ping
- **WHEN** a modern-era request has method `ping`
- **THEN** the gateway answers method-not-found

### Requirement: PROT-9 Completion routing
`completion/complete` (prompt/resource-template argument completion) SHALL be routed to the owning upstream using the
same prefix rules as tools ([BND-3](../bundles/spec.md)).

#### Scenario: Completion for a member prompt
- **WHEN** a client asks `completion/complete` for a prompt presented as `echo__greet`
- **THEN** the request is routed to server `echo` for prompt `greet` rather than answered `-32601`

### Requirement: PROT-11 Capability aggregation
The bundle's capability advertisement (the `initialize` result for handshake clients, the `server/discover` result for
modern clients) SHALL be computed without contacting any member, from the bundle's own prompts and resources and from
the per-server `capabilities` snapshot captured at discovery ([UPS-22](../upstreams/spec.md)) of its enabled
members:

- `tools` always, with `listChanged: true` — the gateway supports tools even with zero members;
- `prompts` and `resources`, each with `listChanged: true`, when the bundle owns one
  ([bundles](../bundles/spec.md)) or at least one member advertises it;
  `resources.subscribe: true` when at least one member supports it;
- `completions` when a bundle prompt offers completions or at least one member advertises it;
- `logging` when at least one member advertises it.

No `extensions` are advertised: the gateway proxies none.

#### Scenario: Zero members
- **WHEN** a client initializes against a bundle with no members and no own prompts or resources
- **THEN** the capabilities are exactly `tools` with `listChanged: true`

#### Scenario: Member capability is aggregated
- **WHEN** one enabled member's snapshot advertises `resources` with `subscribe`
- **THEN** the advertisement includes `resources` with `listChanged: true` and `subscribe: true`

### Requirement: PROT-12 Handshake version negotiation
*(handshake era)* The gateway SHALL negotiate the highest handshake-era version common with the client at its
`initialize`; a client requesting a version older than the supported window fails `initialize` with an error that names
the supported versions. Negotiation with each upstream is independent (PROT-21).

#### Scenario: Supported version
- **WHEN** a client initializes with `2025-11-25`
- **THEN** the result's `protocolVersion` is `2025-11-25`

#### Scenario: Too old
- **WHEN** a client initializes with a version older than the supported window
- **THEN** the gateway answers `-32602` naming the supported versions

### Requirement: PROT-13 Dialects and era detection
The edge SHALL hold a registry of *dialects*, one per supported revision, and pick the dialect once per request from
how the client opens: a request carrying `_meta["io.modelcontextprotocol/protocolVersion"]` is served by that
revision's modern dialect, statelessly; an `initialize` request negotiates a handshake dialect (PROT-12) that is then
recorded on the session; a request carrying `Mcp-Session-Id` is served by its session's dialect. A request that is none
of these is rejected with `-32602` and HTTP 400, the message naming the missing `_meta` fields and the supported
versions, so a dual-era client falls back to `initialize` and an operator sees why. A modern request naming a version
the registry does not hold is rejected with `-32022` (`UnsupportedProtocolVersion`), HTTP 400, and `data.supported`
listing the modern versions. Adding a revision means adding one dialect and registering it; no handler changes
(PROT-22). Handshake dialects can be switched off by configuration (`BUNDLEMCP_LEGACY_PROTOCOL_ENABLED`) once the
deprecation window closes.

#### Scenario: Neither envelope nor session
- **WHEN** a client POSTs `tools/list` with no `_meta` protocol version and no `Mcp-Session-Id`
- **THEN** the gateway answers HTTP 400 with `-32602` naming the supported versions

#### Scenario: Unknown modern version
- **WHEN** a request's `_meta` names protocol version `2099-01-01`
- **THEN** the gateway answers HTTP 400 with `-32022` and `data.supported` listing the modern versions

#### Scenario: Handshake revisions switched off
- **WHEN** `BUNDLEMCP_LEGACY_PROTOCOL_ENABLED` is false and a client sends `initialize`
- **THEN** `initialize` fails with a message telling the client to send the `_meta` envelope

### Requirement: PROT-14 server/discover
`server/discover` MUST be served for every modern dialect, without fanning out to members: `supportedVersions` (the
modern dialects), `capabilities` (PROT-11), `instructions` (the bundle description), the gateway's server info in
`_meta`, and cache hints (PROT-16). Rate limiting treats it like `initialize` ([EP-19](../endpoints/spec.md)).

#### Scenario: Discover
- **WHEN** a modern client sends `server/discover`
- **THEN** the result carries `supportedVersions`, `capabilities`, the bundle description as `instructions`, server info
  in `_meta`, `ttlMs` and `cacheScope`

### Requirement: PROT-15 Mirrored headers
For modern requests the edge MUST validate `MCP-Protocol-Version` against `_meta`, `Mcp-Method` against `method`,
`Mcp-Name` against `params.name`/`params.uri` (decoding the `=?base64?…?=` sentinel), and every `Mcp-Param-*` header
against the argument the presented tool's `x-mcp-header` annotations designate; a mismatch or a missing required header
is HTTP 400 with `-32020` (`HeaderMismatch`). Headers on handshake-era requests are not trusted for policy.
`x-mcp-header` annotations in upstream tool schemas pass through `tools/list` unchanged.

#### Scenario: Header contradicts the body
- **WHEN** a modern request's `Mcp-Method` header differs from its `method`
- **THEN** the gateway answers HTTP 400 with `-32020`

#### Scenario: Mcp-Param header mismatch
- **WHEN** a tool designates argument `region` via `x-mcp-header` and the request's `Mcp-Param-Region` header differs
  from the argument
- **THEN** the call is rejected with HTTP 400 and `-32020` before reaching the upstream

### Requirement: PROT-16 Result shaping and cache hints
Every modern result SHALL carry `resultType` (`"complete"`, or `"input_required"` per PROT-18) and the gateway's server
info in `_meta`. `tools/list`, `prompts/list`, `resources/list`, `resources/templates/list`, `resources/read` and
`server/discover` carry `ttlMs` and `cacheScope`: list results are `public` with a runtime-configurable TTL
(`list_cache_ttl_ms`, default 5 min), invalidated by `listChanged`; `resources/read` of a member resource forwards the
upstream's hint when it gave one and is otherwise `ttlMs: 0`, `private`, while a resource the bundle itself serves is
hinted like a list. Error codes follow the modern table: resource-not-found is `-32602` (it is `-32002` for handshake
clients, and a modern upstream's `-32602` is mapped back for them). `tools/list` order is deterministic (sorted by
presented name). Handshake-era results are byte-for-byte what they were before the modern era was added.

#### Scenario: Cacheable tools list
- **WHEN** a modern client sends `tools/list`
- **THEN** the result carries `resultType: "complete"`, `ttlMs` equal to `list_cache_ttl_ms` and `cacheScope: "public"`

#### Scenario: Resource not found
- **WHEN** a modern client reads a URI no member serves
- **THEN** the error code is `-32602`

#### Scenario: Handshake results unchanged
- **WHEN** a handshake client lists tools on the same endpoint
- **THEN** the result has no `resultType`, `ttlMs` or `cacheScope`

### Requirement: PROT-17 subscriptions/listen
A modern client SHALL open change notifications with one long-lived POST whose response stream first carries
`notifications/subscriptions/acknowledged` echoing the subset of the filter the gateway honours, then only the
notification types acknowledged, each tagged with `_meta["io.modelcontextprotocol/subscriptionId"]` = the request id.
The gateway honours `toolsListChanged` (BND-7 invalidations, delivered cross-replica), and `promptsListChanged` and
`resourcesListChanged` for the bundle's own prompts and resources
([BND-28](../bundles/spec.md)). A member's prompt and resource list changes, and
`resourceSubscriptions`, depend on a standing upstream connection
([ADR-0012](../../../docs/adr/0012-per-call-upstream-connections.md)): they are not delivered, and
`resourceSubscriptions` is omitted from the acknowledgement. The stream sends SSE keep-alive comments, ends with a
completion result on graceful shutdown, and is closed by the client to unsubscribe. GET and DELETE on the endpoint
without an `Mcp-Session-Id` answer 405 ([EP-1](../endpoints/spec.md)).

#### Scenario: Acknowledge and relay
- **WHEN** a modern client opens `subscriptions/listen` asking for `toolsListChanged` and `resourceSubscriptions`, and
  the bundle's curation then changes
- **THEN** the first event acknowledges `toolsListChanged` only
- **AND** a `notifications/tools/list_changed` tagged with the subscription id follows

#### Scenario: Change through another replica
- **WHEN** the listen stream is held by replica B and the bundle is changed through replica A
- **THEN** the stream on B receives the notification

### Requirement: PROT-18 Multi Round-Trip Requests
When an upstream needs client input during `tools/call` for a modern client, the gateway SHALL answer
`resultType: "input_required"` with `inputRequests` and a sealed `requestState`; the client retries the same method with
`inputResponses` and the state, and any replica MUST be able to serve the retry. Two strategies, chosen per upstream
era:

- **Pass-through** (modern upstream): the upstream's own `InputRequiredResult` is forwarded — `inputRequests`
  verbatim, its `requestState` sealed inside the gateway's — and the retry re-issues the call upstream with the
  client's `inputResponses` and the upstream's state. No gateway state exists between the two requests.
- **Park and resume** (handshake upstream): the upstream's server-initiated request is turned into `inputRequests`;
  the in-flight upstream call stays parked on its reply future, bounded by PROT-6; the retry routes the answer to the
  parking replica over the signal bus and the result back to the replica serving the retry. If no replica claims the
  retry (the parking replica is gone), the call is **re-run** with the requests answered from `inputResponses` as they
  recur, so the client still gets a result; this fallback may repeat the upstream's side effects before the
  elicitation and is logged as such.

`requestState` is integrity-protected with the gateway's token cipher and binds the principal, the presented tool and
argument digest, the metering idempotency key and an expiry; a state that fails verification, belongs to another
caller or has expired is rejected with `-32602`. Every leg of one invocation is metered under the idempotency key
sealed in the state ([PROT-26](../protocol/spec.md)): a parked call resumed in place is not re-metered; a pass-through
retry and a re-run fire `pre_call` again with the same key; `post_call` fires once, when the invocation ends. Only
requests the client declared support for in `_meta` capabilities are placed in `inputRequests` (PROT-5). Without token
encryption keys the bridge is unavailable and reports so with an error rather than sealing plaintext. On `prompts/get`
and `resources/read` a modern client is not bridged: a handshake upstream's request for input fails fast, and a modern
upstream's `input_required` is reported as an error.

#### Scenario: Pass-through
- **WHEN** a modern upstream answers `input_required` to a modern client's call
- **THEN** the client receives `resultType: "input_required"` with the upstream's `inputRequests` and a sealed state
  that does not contain the upstream's state in clear
- **AND** the retry with `inputResponses` completes with `resultType: "complete"` and one `post_call` outcome `result`

#### Scenario: Park and resume on another replica
- **WHEN** a handshake upstream elicits during a modern client's call on replica A and the retry reaches replica B
- **THEN** the answer is routed to A and B streams the call's result

#### Scenario: Tampered or foreign state
- **WHEN** a retry carries a `requestState` that was altered, or was sealed for another caller or tool
- **THEN** the gateway answers HTTP 400 with `-32602`

#### Scenario: No encryption keys
- **WHEN** the gateway has no token encryption keys and an upstream asks for input during a modern client's call
- **THEN** the client receives an error saying `input_required` is unavailable

### Requirement: PROT-19 Cancellation by disconnect
Modern `tools/call` responses SHALL always be streamed (`text/event-stream`, progress optional), so the client closing
the stream is an unambiguous cancellation that the gateway applies to the upstream call. `notifications/cancelled` is
still accepted with 202 in both eras.

#### Scenario: Client closes the stream
- **WHEN** a modern client closes a `tools/call` response stream before the result
- **THEN** the upstream call is cancelled and metered as `cancelled`

### Requirement: PROT-20 Per-request log level
A modern request's `_meta["io.modelcontextprotocol/logLevel"]` SHALL enable `notifications/message` at or above that
level on that request's response stream only; requests without it receive none. `logging/setLevel` is not a modern-era
method.

#### Scenario: Logs at the requested level
- **WHEN** a modern client calls a tool with `logLevel` `info` and the upstream logs at `debug` and `info`
- **THEN** only the `info` message appears on the call's response stream

#### Scenario: No log level
- **WHEN** a modern client calls the same tool without a `logLevel`
- **THEN** no `notifications/message` appears on the stream

### Requirement: PROT-21 Per-upstream era
The gateway's upstream client SHALL negotiate per server: `server/discover` first, falling back to `initialize` when the
upstream is handshake-era, unless the server's `protocol_mode` ([UPS-10](../upstreams/spec.md)) pins it. The
negotiated version is recorded at discovery. A handshake upstream's server-initiated requests and a modern upstream's
`input_required` results reach the gateway through one callback shape, so both convert to either client era (PROT-4,
PROT-18). Results of either era are normalised into the gateway's internal model before a dialect shapes them for the
client (PROT-16).

#### Scenario: Auto mode
- **WHEN** a server in `auto` mode that speaks 2026-07-28 is discovered
- **THEN** its recorded `protocol_version` is the modern revision

#### Scenario: Pinned handshake mode
- **WHEN** a server is pinned to the handshake era
- **THEN** discovery negotiates with `initialize` and records a handshake revision

### Requirement: PROT-22 Adding a protocol revision
A new revision SHALL be supported by adding one dialect class (client hop) and, if the upstream SDK does not absorb it,
one adapter (upstream hop), registering the version, running the MCP conformance suite for that revision against the
compose stack, and recording an ADR. Handlers, the relay, metering and audit MUST NOT need to change for a revision that
keeps the method set. The revision lists and the per-revision method sets are read from the MCP SDK's registry
(`mcp_types.version`, `mcp_types.methods`); the gateway keeps only its own decisions, such as the floor of the
handshake window.

#### Scenario: Served revisions come from the SDK
- **WHEN** the gateway starts
- **THEN** the served revisions are the SDK's revisions at or above the gateway's handshake floor

#### Scenario: Method sets come from the SDK
- **WHEN** a modern request names a method the SDK lists only for handshake revisions
- **THEN** it is answered method-not-found without a gateway-side denylist

### Requirement: PROT-24 Metering context
The metering hook SHALL receive, for every metered call, a context carrying the resolved caller identity (`sub` — a
user id, `api_key:<id>`, or `None` when anonymous — and `email`; for an OAuth user also the IdP's `oidc_issuer` and
`oidc_sub`, which are `None` for API-key and anonymous callers), the endpoint, the bundle, the origin server, the
original (unprefixed) tool name and the invocation's `idempotency_key`.

#### Scenario: OAuth caller's IdP subject reaches the hook
- **WHEN** a user signed in through the OIDC provider calls a tool over an OAuth endpoint
- **THEN** the hook's context carries that user's `oidc_issuer` and `oidc_sub` beside the gateway's own `sub`

#### Scenario: API-key caller
- **WHEN** a caller authenticated with an API key calls a tool
- **THEN** the context's `sub` is `api_key:<id>` and `oidc_issuer` and `oidc_sub` are `None`

### Requirement: PROT-25 Built-in pipeline order
The gateway SHALL apply these steps in this order (list and call variants):

1. tool filter — drops disabled tools / rejects disabled calls ([BND-13](../bundles/spec.md))
2. overrides — apply/reverse per-bundle overrides ([BND-14](../bundles/spec.md))
3. profile transform ([EP-13](../endpoints/spec.md))
4. **metering hook** (calls only; no-op unless configured)
5. audit ([operations](../operations/spec.md))

Steps 1–3 are applied when the endpoint's bundle view is composed; steps 4–5 are the `tools/call` pipeline. The order
is bundlemcp's contract regardless of the underlying library.

#### Scenario: Disabled tool never reaches metering
- **WHEN** a client calls a tool that is disabled in the bundle
- **THEN** the call is rejected without a `pre_call` to the metering hook and an audit record with status `denied` is
  written

#### Scenario: Allowed call is metered then audited
- **WHEN** a client calls an enabled tool and the hook allows it
- **THEN** `pre_call` fires before the upstream call, `post_call` after it, and one audit record with status `success`
  is written

### Requirement: PROT-26 Metering hook contract
The metering hook contract (mirroring the first consumer's existing billing API) SHALL be:

- **pre-call**: hook receives `{sub, email, oidc_issuer, oidc_sub, endpoint, bundle, server, tool, idempotency_key}`
  (`email` nullable — the resolved caller's email, which the consumer's ledger uses to attach users; `oidc_issuer` /
  `oidc_sub` nullable — the IdP subject of an OAuth user, the same for every login of that user, for a consumer that
  keys its users on it; `sub` keeps its meaning). It may **allow** or **deny**; the upstream call never happens after
  a deny. A deny with a `user_message` answers the call with a tool result `isError: true` whose only content is that
  text verbatim, so the model relays it to the person; a deny without one answers a structured MCP error carrying the
  hook's `reason`, e.g. `insufficient_credits`.
- **post-call**: hook receives the same identifiers + an `outcome` + `duration_ms`. The outcome is `result` (a tool
  result), `tool_error` (a tool result with `isError: true`: the tool ran), `no_result` (unreachable or timed-out
  upstream, a JSON-RPC error, or the gateway refusing the call after pre-call allowed it) or `cancelled`. The gateway
  does not decide what an outcome costs; the hook does, and a debit followed by anything but `result` is its refund
  trigger to weigh.
- **Unanswered pre-call:** when pre-call raises instead of deciding and the failure policy denies the call, the
  gateway delivers a post-call `no_result` with `duration_ms` 0 for the same `idempotency_key`, since the hook may
  have debited before it failed to answer. Under fail-open the call proceeds and ends with an ordinary post-call.
- **Idempotency across retries:** one `idempotency_key` is minted per client invocation. The gateway-internal
  reactive OAuth retry ([UPS-28](../upstreams/spec.md)) reuses it and does NOT re-fire pre-call. A call that spans
  several requests through Multi Round-Trip Requests ([PROT-18](../protocol/spec.md)) keeps the key
  sealed in its `requestState`: a pass-through retry and a re-run fire pre-call again with the same key, a parked call
  resumed in place does not. Exactly one post-call is delivered per invocation that reached a final outcome after a
  successful or an unanswered pre-call — on that final outcome; a leg that ends in `input_required` delivers none.
- **Crash reconciliation:** if the gateway dies between pre-call and post-call, no refund fires. The audit log
  ([operations](../operations/spec.md)) is the reconciliation source: hook consumers can detect debits with no
  completed audit record and refund out-of-band. This contract is part of the hook documentation.
- Field mapping to the reference consumer's `MeterRequest`: `sub→sub`, `email→email`, `bundle→bundle_slug`,
  `server→server_name`, `tool→tool_name`, `idempotency_key→idempotency_key`; `endpoint` is bundlemcp-side context the
  reference consumer ignores.
- Configured as a Python import path (`BUNDLEMCP_METERING_HOOK`); hook errors follow a configurable policy
  (`BUNDLEMCP_METERING_HOOK_FAIL_OPEN`): fail-open (log, allow) or fail-closed (deny) — default fail-closed.

#### Scenario: Allowed call reports its outcome
- **WHEN** the hook allows a call and the upstream returns a tool result
- **THEN** `post_call` receives outcome `result` and a `duration_ms` under the same `idempotency_key`

#### Scenario: Tool error result
- **WHEN** the upstream returns a result with `isError: true`
- **THEN** `post_call` receives outcome `tool_error`

#### Scenario: Deny with a user message
- **WHEN** the hook denies a call with `user_message` "Your credits are used up"
- **THEN** the client receives a tool result with `isError: true` whose only content is that text
- **AND** the upstream is not called

#### Scenario: Deny without a user message
- **WHEN** the hook denies a call with reason `insufficient_credits` and no `user_message`
- **THEN** the client receives a JSON-RPC error carrying `insufficient_credits` and the upstream is not called

#### Scenario: Pre-call raises under fail-closed
- **WHEN** `pre_call` raises and the fail-open setting is off
- **THEN** the call is denied without reaching the upstream
- **AND** `post_call` is delivered with outcome `no_result` and `duration_ms` 0 under the same key

#### Scenario: Reactive OAuth retry is charged once
- **WHEN** an upstream-OAuth call is retried once after an upstream 401
- **THEN** `pre_call` fired once and `post_call` fires once, with one `idempotency_key`

### Requirement: PROT-27 Versioned hook interface
The hook interface SHALL be a **stable, versioned, documented** Python protocol (`typing.Protocol`, with
`METERING_PROTOCOL_VERSION`) — semver-relevant: breaking it is a major version. Version 2 replaced the post-call
`status` (`success`/`error`) with the `outcome` kind.

#### Scenario: Hook version is published
- **WHEN** an implementer reads the metering hook documentation or the HTTP event bodies
- **THEN** both state protocol version 2 and the `outcome` kinds

### Requirement: PROT-28 No silent errors
The pipeline MUST NOT swallow errors silently; every deny/error path of a `tools/call` SHALL produce a structured MCP
error to the client (or, for a hook deny carrying a `user_message`, the `isError` tool result of PROT-26) and an audit
record.

#### Scenario: Unknown tool
- **WHEN** a client calls a tool name the bundle does not present
- **THEN** the client receives a JSON-RPC error and an audit record with status `denied` is written

#### Scenario: Upstream OAuth not connected
- **WHEN** a client calls a tool of a per-user upstream-OAuth server it has not connected
- **THEN** the client receives a JSON-RPC error carrying the connect hint and an audit record with status `error` is
  written

### Requirement: PROT-29 Out-of-process metering hook
The hook SHALL also be able to run out of process, as a service the gateway reaches over HTTP, so a deployment running
a pinned image needs no Python plugin: `BUNDLEMCP_METERING_HTTP_URL`, a bearer token from
`BUNDLEMCP_METERING_HTTP_TOKEN` (never logged), and `BUNDLEMCP_METERING_HTTP_TIMEOUT` (default 2 s). It cannot be
combined with `BUNDLEMCP_METERING_HOOK`; startup refuses both.

- Every event is a JSON `POST` to that URL: `{protocol_version, event: "pre_call", context}` and
  `{protocol_version, event: "post_call", context, outcome, duration_ms}`, where `context` is the PROT-26 context.
- A pre-call answer is a 2xx JSON decision `{allowed, reason?, user_message?}`. A timeout, a transport error, a non-2xx
  status or a body that is not a decision is an unanswered pre-call (PROT-26), decided by the failure policy.
- A post-call is acknowledged by any 2xx. It is delivered in the background, so a tool result never waits for it, and
  retried on a transport error, a timeout, a 429 or a 5xx: five tries within about a minute, then logged as
  `metering.post_call_failed` with the `idempotency_key`. Any other answer is final. On shutdown, deliveries in flight
  get a few seconds to finish.

#### Scenario: Only tools/call is metered
- **WHEN** a client initializes, lists tools and calls one tool against an endpoint with an HTTP hook
- **THEN** the hook service receives exactly one `pre_call` and one `post_call`

#### Scenario: Hook service does not answer
- **WHEN** the hook service times out on `pre_call` under the default fail-closed policy
- **THEN** the call is denied without reaching the upstream and a `post_call` with outcome `no_result` is sent

#### Scenario: Post-call retried, then given up
- **WHEN** every delivery of a `post_call` fails with a transport error
- **THEN** the gateway tries it five times within a minute and then logs `metering.post_call_failed` with the
  `idempotency_key`

#### Scenario: A 4xx is final
- **WHEN** the hook service answers a `post_call` with 400
- **THEN** the gateway does not retry it

#### Scenario: Both hook kinds configured
- **WHEN** both `BUNDLEMCP_METERING_HOOK` and `BUNDLEMCP_METERING_HTTP_URL` are set
- **THEN** settings validation fails at startup

## Out of scope

### Protocol passthrough

- Persisting/replaying server→client requests across a *client* disconnect — if the client's stream is gone, pending
  upstream requests fail with the call (a parked modern call waits only for its PROT-6 budget).
- Rate-limiting relayed notifications (revisit if an upstream floods).
- Proxying protocol extensions (Tasks, MCP Apps) — advertised as unsupported (PROT-11) until a dedicated spec covers
  them.

### Tool-call pipeline and metering hook

- A general plugin marketplace or dynamic loading of arbitrary third-party middleware; one configured hook + built-ins
  is the v1 surface.
- The billing logic itself (ledger, pricing, refunds) — application layer.

## Notes

### Protocol passthrough

Origin: new — metamcp covered only fragments (timeouts, progress-token forwarding). Motivating case: the hyperframes
upstream blocks ~130 s per render; without progress-aware timeouts and cancellation such calls are unusable through a
gateway. MCP revision 2026-07-28 replaced the protocol's stateful core (no `initialize`, no `Mcp-Session-Id`, no GET
stream, no server-initiated requests); the gateway speaks every supported revision on both hops so any client era works
with any upstream era.

Decisions: the downstream half of the relay is built on bundlemcp's own endpoint edge (SSE call responses + GET event
stream) and the upstream half on the FastMCP client's progress, elicitation, sampling and roots handlers; cross-replica
routing is a publish-only RESP `bmcp:signal:*` bus feeding per-replica registries of streams, calls and reply futures
([ADR-0016](../../../docs/adr/0016-relay-design.md)). Dialects and the dual-era edge:
[ADR-0029](../../../docs/adr/0029-dialects-and-dual-era-edge.md), [ADR-0030](../../../docs/adr/0030-fastmcp-4.md) —
the SDK exposes the raw `InputRequiredResult` and accepts `inputResponses`/`requestState` on the retry, so PROT-18
pass-through is native.

Pooling-dependent residual: any upstream→client push that must arrive between calls — `notifications/resources/updated`,
upstream `notifications/message` and upstream `*/list_changed` outside an active call — requires a persistent upstream
connection, which the per-call-connection model (ADR-0012) does not provide. `resources/subscribe` is accepted but no
update is pushed.

### Tool-call pipeline and metering hook

Origin: improvement — metamcp had a middleware chain; its metering hook was only a code comment. The contract mirrors
the first consumer's billing meter router. The HTTP hook and the outcome kinds are recorded in
[ADR-0042](../../../docs/adr/0042-http-metering-hook-and-outcome-kinds.md); the implementer-facing contract is
`docs/integrate/metering-hook.md`.

Open question: whether the hook should also see `tools/list` (e.g. to hide tools a user has no entitlement for) —
deferred; the reference consumer's current model gates at call time.
