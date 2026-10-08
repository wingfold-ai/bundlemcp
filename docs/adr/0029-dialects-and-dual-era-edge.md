# ADR-0029: Protocol dialects and a dual-era MCP edge

**Status:** accepted · **Date:** 2026-09-05 · **Amended by:**
[ADR-0035](0035-front-controller-protocol-adapters-and-admission-pipeline.md) · **Amends:**
[ADR-0011](0011-own-streamable-http-edge.md), [ADR-0016](0016-relay-design.md),
[ADR-0021](0021-mcp-surface-completion.md), [ADR-0027](0027-mcp-edge-method-handlers.md)

## Context

MCP revision 2026-07-28 (final, 28 July 2026) removed the four things the edge is built around: the `initialize`
handshake, the `Mcp-Session-Id` session, the HTTP GET event stream, and server-initiated requests. In their place:
per-request `_meta` (version, client info, capabilities), a mandatory `server/discover`, `subscriptions/listen` for
change notifications, and Multi Round-Trip Requests (an `input_required` result the client answers by retrying). It also
mandates `resultType` on every result, cache hints on list and read results, mirrored `Mcp-Method`/`Mcp-Name` headers,
and renumbers error codes.

The edge on `main` (`gateway/mcp_endpoint/`) hard-codes one wire shape and serves 2025-11-25 and earlier. A modern-only
client gets a plain 404 on its first request. Dual-era clients fall back to `initialize` and lose nothing but a round
trip; that is why nothing is broken today — and it is why the legacy path must stay first-class: as of 2026-09-05
Copilot is the only major client on the modern era, while Claude, ChatGPT, Gemini CLI and Cursor still open with
`initialize`. The spec's deprecation policy keeps the handshake era alive for at least twelve months.

The requirement (spec 32, PROT-13 to PROT-22) is every pairing of client era and upstream era, the newest version each
side supports, and room for the next revision without another redesign.

## Decision drivers

- The spec itself defines the dual-era server ("selects its behaviour from how the client opens") and permits both eras
  on one endpoint; one URL per endpoint is a product requirement (EP-1).
- A dialect object localises the revision-specific surface to one class per revision. The alternative — `if era ==`
  branches in handlers — is the method-chain shape ADR-0027 removed.
- Pass-through for modern↔modern is stateless by construction and was proven in the ADR-0030 spike; parking is needed
  only where the upstream cannot suspend, and it reuses the relay machinery ADR-0016 already built rather than adding a
  second distributed mechanism.
- Park-and-resume over re-run because re-running repeats an upstream tool's side effects before the elicitation; re-run
  remains as the fallback because a lost replica should degrade to "the client still gets a result", the same promise
  SES-13 makes for streams.

## Decision

- **A `WireDialect` per revision, chosen once per request.** The edge holds a `DialectRegistry` (`gateway/dialect/`)
  mapping version strings to dialect objects. A dialect owns everything that differs between revisions on the client
  hop: how a request is admitted (session record vs `_meta`), the method set it may call, how a result is shaped
  (`resultType`, server info, cache hints), its error-code table, which notification channel it uses, how it asks the
  client for input, and what its cancellation signal is. The edge selects the dialect from how the client opens — modern
  `_meta`, an `initialize`, or an `Mcp-Session-Id` — and nothing downstream branches on the version again. Adding a
  revision is adding a dialect class, the same shape of change as adding a method handler (ADR-0027).
- **A version-neutral core.** Handlers, `ToolCall`, audit and metering see `RequestContext` (replacing `SessionContext`;
  its `session` is `None` for a modern request), neutral results with a `CacheHint`, `InputRequest` / `InputResponse`
  value objects and `NeutralError` codes. Dialects translate at the edge only.
- **Handshake dialects are unchanged behaviour.** Session records, the GET stream, `ping`, `logging/setLevel`,
  server-initiated relay and the -32002 resource error stay exactly as they were for `initialize` clients; their tests
  are not modified. A `legacy_protocol_enabled` setting removes those dialects from the registry when the deprecation
  window closes.
- **Streams are keyed by a `StreamKey`, not a session.** The stream registry identifies a live stream by endpoint,
  bundle and a stream id (session id for handshake clients, request id for `subscriptions/listen`), so list-changed
  fan-out and cross-replica delivery (ADR-0016) serve both eras through one registry and one signal bus.
- **Modern `tools/call` always streams.** With every response an SSE stream, the client closing it is the unambiguous
  cancellation the revision prescribes; the buffered JSON path remains for handshake clients without a progress token.
- **MRTR in two strategies, selected by the upstream's era.** Against a modern upstream the gateway is a *pass-through*:
  the upstream's own `InputRequiredResult` is forwarded and its `requestState` sealed inside the gateway's; the retry
  re-issues the call upstream with the answers. No gateway state exists between the two requests. Against a handshake
  upstream the gateway *parks*: the upstream call stays blocked on its reply future on the replica that holds it, the
  client receives `input_required`, and the retry — on any replica — routes the answer to the parked call over the
  signal bus (`ReplySignal`) and the result back (`ResultSignal`). If no replica claims the retry, the call is re-run
  with the answers pre-loaded. `requestState` is sealed with the token cipher (ADR-0017) and binds principal, tool,
  argument digest, idempotency key and expiry.
- **Modern upstream, handshake client is the relay unchanged.** The upstream SDK turns a modern upstream's
  `input_required` into the same handler callback a handshake upstream's server-initiated request produces (ADR-0030),
  so the existing GET-stream relay serves it without knowing.

## Alternatives considered

_Not recorded at the time of the decision._

## Consequences

### Positive

- Every client era talks to every upstream era; modern clients get a stateless edge with cache hints and header routing;
  handshake clients see no change.
- The next revision is one dialect class plus a conformance run (PROT-22).
- `SessionContext` and the session-keyed registries disappear from the handlers; only dialects and the edge know what a
  session is.

### Trade-offs

- Two MRTR strategies to test and to explain; the re-run fallback can repeat side effects and is logged when it happens.
- `subscriptions/listen` honours only `toolsListChanged` until upstream pooling exists (ADR-0012); prompt/resource
  list-changed and resource subscriptions are omitted from the acknowledgement.
- Streaming every modern `tools/call` costs an SSE frame for the buffered case; accepted for an unambiguous cancellation
  signal.

