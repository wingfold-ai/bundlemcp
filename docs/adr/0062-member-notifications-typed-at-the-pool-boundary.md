# ADR-0062: Member notifications are typed at the pool boundary

**Status:** accepted · **Date:** 2026-10-29 · **Extends:** [ADR-0027](0027-mcp-edge-method-handlers.md),
[ADR-0054](0054-upstream-session-pooling.md)

## Context

ADR-0054 has pooled upstream sessions hear their members between calls: a handshake-era session through the SDK's GET
stream, a modern one through a standing `subscriptions/listen`. What they heard reached the application as JSON-RPC
dicts. The pool dumped each SDK notification to a dict, and rebuilt one by hand for each listen event. The application
router then branched on `method` and read `uri` and `level` out of `params` by key, the dispatch conditional ADR-0027
removed from the MCP edge. Because the dict was relayed as it arrived, a member's own `_meta` reached the client,
although it described the member's hop to the gateway (audit finding S8, 2026-10-29).

Two further gaps sat in the same path (audit finding S23):

- The pool subscribed handshake-era members through the SDK's `subscribe_resource` and `unsubscribe_resource`, which
  MCP SDK 2.3 marks deprecated for every session. Yet `resources/subscribe` is the only way a 2025-era server sends
  resource updates.
- The pool re-opened a lost listen stream but did not refetch. The protocol replays nothing, so a change made while the
  stream was down was never heard.

## Decision drivers

- A member's notification is parsed once. Past the sink contract, no code reads a JSON-RPC key.
- A new kind of notification is a model and a handler, not a branch.
- The application layer names no driver (ADR-0023/0033), so it cannot take the SDK's types.
- Handshake-era members keep their resource subscriptions, without a deprecated SDK call.

## Decision

- **A typed union beside the sink contract.** `application/contracts/upstream/member_notification.py` holds three
  frozen models: `MemberListChanged` (which list, a `ListedKind`), `MemberResourceUpdated` (the URI) and
  `MemberLogMessage` (level, logger, data). `MemberNotification` is their union, discriminated by `kind`.
  `UpstreamNotificationSink.received` takes the union. A relayed update or log message is rebuilt from the model's own
  fields by its `notification()`, so the member's `_meta` stops at the pool. `LogLevel`, the eight MCP levels as a
  `Literal`, lives in `domain/sessions/log_levels.py`, and `LOG_LEVELS` is derived from it.
- **Translation once, in infrastructure.** `infrastructure/fastmcp/member_notification_translation.py` maps the SDK's
  handshake notifications, listen events and log messages to the union through tables keyed by SDK type. A type not in
  a table, or one that does not validate (an empty URI, a level outside the eight), is logged at debug and dropped.
- **A handler registry in the application.** `MemberNotificationRouter` implements the sink and holds one handler per
  model type: `MemberListChangeHandler` (the re-discovery gate of PROT-10), `MemberResourceUpdateHandler` and
  `MemberLogMessageHandler`. A type with no handler is logged and ignored. The registry has the shape of the MCP edge's
  `MethodRegistry`; the composition root builds it.
- **One resource-watch strategy per era.** When a pooled session connects and its revision is known, it is given a
  `ResourceWatch`. `SubscribeResourceWatch` sends `resources/subscribe` and `resources/unsubscribe` as explicit
  requests through `ClientSession.send_request`, which carries no deprecation. `ListenResourceWatch` changes the
  session's watched URIs and re-opens its listen stream. `PooledLease.subscribe` and `unsubscribe` delegate to it.
- **A re-opened listen stream refetches.** After every acknowledged re-open that is not its task's first, the listen
  loop reports each list the stream listens for as changed and each URI it watches as updated. The list changes pass
  through the re-discovery gate, so replicas re-opening together still discover once per list. A filter change starts
  a new task, whose first open reports nothing.

## Alternatives considered

- **Pass the SDK's types to the application.** The application may not name a driver, and the handshake notifications
  and listen events are two SDK families for the same facts.
- **A `match` over the union.** Type-checked, but it is the dispatch conditional again, and one class would hold every
  handler's collaborators.
- **Keep the SDK helpers and filter the warning.** Hides the signal, and breaks the day the SDK removes the helpers.
- **Re-listen without refetching.** Loses every change made while the stream was down, against the SDK's own guidance
  ("re-listen and refetch").

## Consequences

### Positive

- The relayed notification is built from what the member said, not from how it said it, and a malformed one stops at
  the pool.
- Adding a notification kind touches a model, a converter and a handler; no dispatcher changes.
- The test run no longer warns that `resources/subscribe` is removed, and a later SDK without the helpers does not
  break handshake-era subscriptions.
- A modern member's change made while its listen stream was down still reaches clients.

### Trade-offs

- Clients no longer see a member's `_meta` on relayed log messages and resource updates. MCP gives a member's `_meta`
  no meaning on another hop, and a modern member's listen events already reached clients without it.
- After a re-open, clients may see a list change and a resource update that carry no new content. MCP clients treat
  both as "fetch again". A member whose stream flaps costs one gate check per flap and no extra discovery.
- `logging/setLevel` to handshake-era members still goes through the SDK helper the SDK deprecates. It is sent from the
  MCP edge, not the pool, and is left to a separate change.
