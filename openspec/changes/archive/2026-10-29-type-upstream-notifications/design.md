# Design

## Context

See [proposal.md](proposal.md). The current code works as follows (paths under `packages/bundlemcp/bundlemcp/`):

- **The pool hears members in three places**, all in `infrastructure/fastmcp/pooled_upstream_sessions.py`:
  - `message_handler` (around line 461) receives every SDK notification on a handshake-era session, keeps the four in
    `SERVER_NOTIFICATIONS` (lines 42-47) and dumps each to a dict with `model_dump(by_alias=True, mode="json",
    exclude_none=True)`. The member's `_meta`, if any, stays in the dict.
  - `log_handler` (around line 446) wraps a log message's params, again dumped whole, in a hand-built
    `notifications/message` dict when no request owns it and the session is bound to a client's session.
  - `_listen` / `_listened` (lines 415-432) read a modern member's `subscriptions/listen` stream through the SDK's
    `listen()` driver and rebuild a dict per typed event through `_LISTEN_EVENTS` (lines 51-55).
- **`_notify` (lines 471-483)** hands the dict to the `UpstreamNotificationSink` contract
  (`application/contracts/upstream/upstream_notification_sink.py`), whose signature is
  `received(server, notification: dict[str, Any], *, bound_to)`.
- **`UpstreamNotificationRouter.received`** (`application/serving/upstream_notification_router.py:72-88`) branches on
  `notification.get("method")`, then `_resource_updated` and `_log_message` dig `uri` and `level` out of `params`
  (lines 110 and 118) and deliver the original dict through `SignalBus.deliver`.
- **Resource subscriptions upstream** go through `PooledLease.subscribe` / `unsubscribe` (lines 170-181): on a
  handshake-era session they call `client.session.subscribe_resource(uri)` / `unsubscribe_resource(uri)`, which MCP SDK
  2.3 decorates `@deprecated(..., category=MCPDeprecationWarning)` for every session (`mcp/client/session.py:970-991`);
  on a modern session they only change `session.subscriptions` and call `relisten`.
- **The SDK's listen driver** is `mcp.client.subscriptions.listen(session, ...)`. `mcp.Client.listen()` is a thin
  wrapper over it that adds response-cache eviction; FastMCP 4.1.4's `fastmcp.Client`, which the pool holds, has no
  `listen` at all. The audit's "move to `Client.listen()`" is therefore already done in substance: the pool calls the
  same driver on `client.session`. What the driver documents and the pool does not do is the second half of "re-listen
  and refetch" (`mcp/client/subscriptions.py:1-8`).
- **Explicit requests are not deprecated.** `ClientSession.send_request(request, result_type)` is public and carries no
  warning; `mcp_types.SubscribeRequest` and `UnsubscribeRequest` are documented as "sent on sessions negotiating
  <= 2025-11-25", which is exactly where the pool sends them.

## Goals / Non-Goals

**Goals:**

- A member notification is parsed once, in infrastructure, and nothing past the sink contract reads a JSON-RPC key.
- Adding a notification kind means adding a model and a handler, not a branch.
- No `MCPDeprecationWarning` from the pool, with handshake-era members keeping their subscriptions.
- A modern member's change made while the gateway's listen stream was down still reaches the clients.

**Non-Goals:**

- `logging/setLevel` to handshake-era members (`api/mcp/dispatch/handlers/logging_set_level_handler.py:39`), which the
  SDK deprecates the same way. It is sent from the MCP edge, not the pool.
- Splitting `PooledUpstreamSessions` into a lifecycle state machine (audit S11) or typing capability dicts (audit S9).
  This change touches the pool only where notifications and subscriptions pass through it.
- Typing the `SignalBus` payload. Streams carry JSON-RPC dicts on every path; the typed models produce one at the
  point of delivery.

## Decisions

### A typed union beside the sink contract (application)

`application/contracts/upstream/member_notification.py` holds three frozen models and their union:

- `MemberListChanged(listed: ListedKind)` — `ListedKind` is a `StrEnum` of `tools`, `prompts`, `resources`.
- `MemberResourceUpdated(uri: str)` — `uri` with `min_length=1`.
- `MemberLogMessage(level: LogLevel, logger: str | None, data: JsonValue)` — `logger` is `None` when the member named
  none, which the protocol allows.
- `MemberNotification = Annotated[MemberListChanged | MemberResourceUpdated | MemberLogMessage, Field(discriminator=
  "kind")]`, each model carrying a `kind: Literal[...]`.

`MemberResourceUpdated` and `MemberLogMessage` each have a `notification()` method returning the JSON-RPC
notification the gateway relays, built from its own fields only. That is where the member's `_meta` stops (PROT-7,
PROT-23). `MemberListChanged` has none: a list change is never relayed as heard, since re-discovery announces it
through `ListChangedNotifier` (implementation note: the plan gave every model the method; one with no caller was left
out). `ListChangedNotifier` already builds its
notifications the same way in the application layer, so this adds no new kind of code there.

`LogLevel` is a `Literal` of the eight MCP levels, added to `domain/sessions/log_levels.py`, with `LOG_LEVELS` derived
from it through `get_args` so the tuple and the type cannot drift. The existing users of `LOG_LEVELS` (the setLevel
handler, the stateless adapter) are unchanged.

`UpstreamNotificationSink.received(server, notification: MemberNotification, *, bound_to)` replaces the dict
parameter.

Alternatives considered:

- **Reuse the SDK's types** (`mcp.shared.subscriptions.ServerEvent`, `mcp_types.*Notification`). The application layer
  may not name a driver (import contract "Domain and application are driver-free", ADR-0023/0033), and the two SDK
  families (handshake notifications and listen events) are different types for the same fact.
- **Put the models in `domain/`.** They carry no rule; they are the vocabulary of one contract, like
  `UpstreamLeaseRequest` beside `UpstreamSessionPool`.
- **One class per list kind**, as the SDK does. The three list changes differ only in which list and in the reaction,
  which the handler maps from `ListedKind`; three classes would triple the registry for one behaviour.

### Translation once, in infrastructure

`infrastructure/fastmcp/member_notification_translation.py` holds two functions:

- `from_server_notification(message) -> MemberNotification | None` for the SDK notifications of a handshake-era
  session, via a `{SDK type: converter}` table. A type not in the table returns `None` and is not passed on, as
  `SERVER_NOTIFICATIONS` filters today.
- `from_listen_event(event) -> MemberNotification` for the typed events of a listen stream, via the same kind of table
  keyed by the SDK's event types.

`log_handler` builds a `MemberLogMessage` from the SDK's `LoggingMessageNotificationParams` through a third function
in the same module, `from_log_message`. A message the SDK hands
over that does not validate into the model (an empty URI, a level outside the eight) is logged at debug and dropped
there, which is what the router's key-digging did implicitly. `SERVER_NOTIFICATIONS`, `_LISTEN_EVENTS`, `_listened` and
the dict building in `_handlers` go away. `_notify` takes a `MemberNotification` and logs `kind` instead of `method`.

### A handler registry in the application layer

`application/serving/member_notifications/` replaces `upstream_notification_router.py`:

- `MemberNotificationHandler`, a `Protocol` with `async def handle(server, notification, *, bound_to) -> None`.
- `MemberListChangeHandler` — the `REDISCOVER_KEY` gate, re-discovery and the announce-on-failure of
  today's lines 76-84 and 90-107, with `_MEMBER_LISTS` keyed by `ListedKind`.
- `MemberResourceUpdateHandler` — the subscription index lookup and delivery of today's lines 109-115.
- `MemberLogMessageHandler` — the level check of today's lines 117-123, and the `bound_to is not None` condition of
  line 87, which moves into the handler that needs it.
- `MemberNotificationRouter`, which implements the sink and holds `dict[type[MemberNotification], handler]`. An
  unregistered type is logged and ignored rather than raising into the pool's listener.

The composition root (`main/composition_root.py:264-271`) builds the three handlers and the router. The router is the
same shape as `MethodRegistry` (ADR-0027); the handlers declare their collaborators in their constructors and nothing
else.

Alternatives considered:

- **A `match` statement over the union with `assert_never`.** Type-checked and short, but it is the dispatch
  conditional again in another syntax, and one class would keep all six collaborators.
- **`functools.singledispatchmethod`.** Dispatches on type, but registers by decorator on one class, so the
  collaborators still share a constructor.

### One resource-watch strategy per era (infrastructure)

`PooledLease.subscribe` and `unsubscribe` branch on `session.is_modern`. A small strategy chosen once, when the
session connects and its negotiated revision is known, replaces the branch:

- `SubscribeResourceWatch` (handshake era) sends `SubscribeRequest` / `UnsubscribeRequest` through
  `client.session.send_request(..., EmptyResult)`. No deprecated helper is called, so no warning, and the request
  still matches what a 2025-era server expects.
- `ListenResourceWatch` (2026-07-28) changes the watched set and asks the pool to re-open the listen stream with the
  new filter, as `relisten` does today.

Both live in `infrastructure/fastmcp/resource_watch.py`; `PooledSession` holds the one it was connected with, in a
`resource_watch` field that is None until its transport is opened. `ListenResourceWatch` holds the pool's `relisten`,
so `PooledLease` no longer needs the `relisten` callback the pool-states change gave it, and loses that field. The
existing ordering is kept: `unsubscribe` drops the URI from the session's set before the upstream call, since the
subscription may have been made through another replica's transport (line 177).

Alternatives considered:

- **Keep the helpers and filter the warning** (`warnings.catch_warnings` or a pytest filter). Hides the signal and
  still breaks the day the SDK removes the helpers.
- **Stop subscribing handshake-era members.** Breaks PROT-23 for every 2025-era member, which is most of them today.

### Refetch when a listen stream is re-opened after a loss (infrastructure)

`_listen` already loops: it re-opens the stream a second after it ends, whether gracefully or by `SubscriptionLost`.
The loop gains one fact, whether this task has had an acknowledged stream before. After every acknowledged re-open
that is not the task's first, it passes to the sink, through the normal `_notify` path:

- one `MemberListChanged` per list in the filter the member acknowledged for the re-opened stream
  (`tools_list_changed` and so on), and
- one `MemberResourceUpdated` per URI in that acknowledged filter's `resource_subscriptions`.

The acknowledged filter, not the requested one, is used: it is what the stream listens for, and the SDK's
`ListenHandler` acknowledges every kind it is asked for.

The list changes go through the existing re-discovery gate, so several sessions and replicas re-opening at once (an
upstream restart) still cause one discovery per list per gate window (PROT-10). A filter change is not a loss:
`relisten` cancels the task and starts a new one, whose first open refetches nothing.

## Risks / Trade-offs

- [A member relied on its `_meta` reaching clients] → nothing in MCP gives a member's `_meta` meaning on another hop,
  and a modern member's listen events already reach clients without it. The proposal lists it as a behaviour change.
- [An upstream restart fans out one synthetic `resources/updated` per pooled session that watches the URI, each
  delivered to every stream subscribed to it] → the same multiplicity a genuine update has today; clients re-read on
  it. Collapsing it is a separate change if it shows up in practice.
- [A flapping listen stream refetches every second] → re-discovery is gated per list (`REDISCOVER_GATE_SECONDS`), so
  the cost is one gate check per flap and no extra discovery. The resource updates are cheap stream writes.
- [A notification type the SDK adds later is silently dropped] → the translation table logs an unknown type at debug,
  and adding a kind is one model, one converter and one handler.

## Testing a modern member

FastMCP's own server does not serve `subscriptions/listen`; the SDK's `MCPServer` registers a `ListenHandler`, which
FastMCP's low-level server does not. The member-notification API tests therefore register the SDK's `ListenHandler`
(over an `InMemorySubscriptionBus`) on the test upstream's low-level server, as they already register
`resources/subscribe`, and wrap it to record each requested filter. Events are published on the bus; closing the
handler's streams stands in for a lost stream, since the pool re-opens a stream that ends either way.

## Migration Plan

No data or configuration migration. Deploy; rollback is the previous image. Nothing is stored in the new shape: member
notifications live only between the pool and the sink, and streams receive the same JSON-RPC methods as before.
