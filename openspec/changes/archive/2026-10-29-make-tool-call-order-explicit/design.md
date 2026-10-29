# Design

## Context

See proposal.md for the motivation. Every piece of this change lives in the **api layer** (`bundlemcp/api/mcp/`). It
names application contracts (`StreamRegistry`, `CallHandle`) and domain values (`CallTimeouts`, `SessionRecord`), and
that is already allowed there. No domain, application or infrastructure module changes, so `lint-imports` is unaffected.

How the code sequences a call today:

- `ToolCall.run()` (`tool_call.py:153-189`) resolves the headers, asks the chain to admit, reads the call timeouts, and
  registers a call handle when the request has an id. It then hands `self` to `StreamedCallResponse` or
  `BufferedCallResponse`.
- The renderers call back into `execute`, `conclude`, `finish` and `disconnected` (`call_response.py:49-118`).
- The streamed renderer first calls `attach(events)` (`call_response.py:93`). The buffered renderer never does.
- The buffered renderer is only reached in the session era. `run()` streams every stateless request
  (`tool_call.py:187`). Its input channel is therefore always `None`: `_channel` returns `None` for
  `ProtocolEra.SESSION` before it reads `_events` (`tool_call.py:345-346`). This is the fact that makes `_events` safe
  to leave `None` today, and the code never states it.
- `handle` is `None` when the client sent no request id. That `None` is honest: `UpstreamCall` documents it
  (`upstream_call.py:73`) and checks for it (`upstream_call.py:180`).
- `StreamRegistry.unregister_call` pops with a default (`infrastructure/inprocess/stream_registry.py:50-51`), so it is
  idempotent.
- `CallHandle.cancel_event` is only awaited while the upstream call is running (`upstream_call.py:180-182`).

How the session era is wired:

- `SessionMcpAdapter._admit_session` (`session_adapter.py:90-118`) always returns a context built from a loaded
  `SessionRecord` (`_session_context`, lines 121-133). Its return type is `RequestContext`, whose `session` is optional
  (`request_context.py:31-34`).
- `UpstreamLeases.end_session` is called only from `close_session` (`session_adapter.py:87`).

How the member fan-out works:

- `MemberFanout.merged()` (`member_fanout.py:199-236`) reads the shareable snapshots once. It then walks the members in
  order, awaiting `_ask` for every member without a snapshot, and folds the entries into `items` using the `seen` set.
- `first()` (lines 179-197) has one caller, `resources_read_handler.py:74`.
- `each()` (lines 160-167) has no caller in the package or the tests.
- No per-member timeout bounds a list call today. A hanging member holds the list until its transport gives up.

## Goals / Non-Goals

**Goals:**

- Every value a tool-call step needs is a constructor field or a required parameter. No attribute is assigned outside
  `__init__`, and no assert narrows an optional in `tool_call.py`, `session_adapter.py` or `upstream_leases.py`.
- A live list is as slow as its slowest member, and returns the same entries in the same order as before (BND-38).
- `BridgedRead` follows the Pydantic rule.

**Non-Goals:**

- The other asserts in the package (`config_import_service.py`, `pooled_upstream_sessions.py`, the two exception
  handlers, and others). They live in other layers or belong to other audit findings.
- The `tuple[dict, dict]` that `UpstreamLeases.headers` returns. Typed page and value objects that cross layers are
  findings S7 and S16, and this tuple stays inside the api layer.
- Replacing `time.time()` in `_pause` and `seal` with the injected clock. That is finding S15.
- A per-member timeout on list calls. It would be new behaviour that needs its own requirement.
- Making `resources/read` concurrent. BND-8 requires the first owner in member order, and asking members past the owner
  would contact upstreams for no reason (ADR-0043).

## Decisions

### `AdmittedCall`: a parameter object, built once the chain admits

`api/mcp/tool_call/admitted_call.py` is a frozen `BaseModel` with four fields:

- `forwarded: dict[str, str]`
- `credentials: dict[str, str]`
- `timeouts: CallTimeouts`
- `handle: CallHandle | None`, where `None` means the request has no id, so nothing can cancel the call

`run()` takes `received = time.monotonic()` and resolves the headers. When the chain refuses, it calls
`_refuse(refusal, received)`. Otherwise it builds the `AdmittedCall` and calls `renderer.render(self, admitted)`.

These steps now take the admitted call as their first argument, and none of them reads an attribute that might be
unset: `execute`, `_execute`, `_upstream_call`, `conclude`, `finish`, `disconnected`, `_pause` and `_release`.

The `_forwarded`, `_credentials`, `_timeouts`, `_handle`, `_events` and `_admitted_at` attributes and the `attach`
method are deleted.

*Alternatives:*

- **Keep the attributes and replace each assert with an explicit `if ... is None: raise`.** This survives `-O`, but it
  still leaves the order implicit and adds four unreachable branches.
- **A second class (`RunningToolCall`) that `run()` constructs.** It would be a cleaner type-state split. It would also
  move about 200 lines and every `self._support` reach into a new class for the same gain. The parameter object fixes
  the defect with a much smaller diff, and the class can still be split later if `ToolCall` grows.

### The input channel is chosen by the renderer that owns the events

`execute` takes `channel: InputChannel | None` instead of computing it.

- `StreamedCallResponse` builds its `CallEvents` and gets the channel from `call.input_channel(admitted, events)`. That
  method is today's `_channel` with `events` made a required parameter: `None` for the session era, a
  `PreansweredChannel` for a re-run, and otherwise a `ParkingChannel` whose `seal_state` is a closure over
  `_pause(admitted, "parked")`.
- `conclude(admitted, events, …)` takes the same events as a parameter.
- `BufferedCallResponse` passes `channel=None`. That is exactly what `_channel` returns today in the only era that
  reaches the buffered path.

The pairing "streamed ⇔ has events" is now in the types rather than in a comment.

*Alternative:* pass `events: CallEvents | None` into `execute` and keep `_channel` inside `ToolCall`. This still needs a
`None` branch that cannot be reached, which is the same assert under a different name.

### `SessionRequestContext` narrows `session` by subclassing

`api/mcp/protocol/session_request_context.py` declares `SessionRequestContext(RequestContext)` with
`session: SessionRecord` as a required field, with a description.

- `_admit_session` and `_session_context` return it.
- `handle_post`, `open_stream` and `close_session` read `request_ctx.session` without narrowing it.
- `UpstreamLeases.end_session(ctx: SessionRequestContext)`.

`MethodRegistry.dispatch` and every handler still take `RequestContext`, so handlers still cannot tell which era they
are serving (ADR-0035). A subclass instance is a `RequestContext`.

*Alternatives:*

- **Make `RequestContext.session` required.** This is wrong: a modern request has no session, and the optionality rule
  in `.claude/docs/pydantic-models.md` names exactly this case.
- **Split `RequestContext` into sibling stateless and session types.** Handlers would then have to accept a union and
  would learn the era, which is what the front-controller design avoids.
- **Return the record next to the context from `_admit_session`.** That means a tuple, or a second model that carries
  the same record twice.

`upstream_leases.py:138` gets no new type. The assert there narrows `lease.binding` after a boolean computed one line
earlier. The condition becomes `session is not None and lease.binding is not None and lease.binding != request.binding`
and the assert goes. `lease(request, session: SessionRecord | None)` keeps its optional parameter, because unbound
leases are real.

### `RelayMode` is a `Literal` alias owned by `request_state.py`

`RelayMode = Literal["parked", "passthrough"]` is declared in `relay/request_state.py` and exported from
`relay/__init__.py`. `RequestState.mode`, `ToolCall._pause(admitted, mode: RelayMode, …)` and the bridge's
`seal(mode: RelayMode, …)` use it.

*Alternative:* a `StrEnum`. Sealed tokens would keep the same strings, but the existing `state.mode == "passthrough"`
comparisons and the tests that build `RequestState(mode="parked")` would need edits for no gain. A `Literal` is exactly
the type the field already has, given a name.

### `MemberFanout`: gather, then fold in member order

`merged()` does three things in order:

1. Split the capable members into those with a stored listing and those to ask live.
2. Run `asyncio.gather(*(self._ask(ctx, s, call) for s in live))`.
3. Fold over `members` in member order, taking each member's entries from the snapshot or from its gathered answer,
   with the existing `seen` and `present` logic unchanged.

Because the fold order is the member order, which entry wins and which collision is logged do not depend on response
timing (BND-1, BND-8, BND-38).

*Why `gather` over `TaskGroup`:* `_ask` never raises `Exception`, because it converts every failure into `None` and a
log line. A `TaskGroup` would therefore buy nothing. `gather` returns the answers positionally, which is the fold's
input. A `CancelledError` (the client went away) still cancels every member request.

The other two fan-out changes:

- **`first()`** keeps its sequential loop, but its body becomes `answer = await self._ask(ctx, server, call)`, returning
  on the first non-`None` answer. The log lines become `passthrough.member_unconnected` and
  `passthrough.member_failed` with `exc_info`, the same as `merged()`. A member whose successful answer is `None` was
  already treated as "no answer" by the caller (`resources_read_handler.py:80`), so that path behaves as before.
- **`each()`** is deleted. It has no caller, and the alternative is to keep a sequential twin of the code this change
  makes concurrent.

### `BridgedRead` becomes a frozen `BaseModel`

`BridgedRead` stays in `input_required_bridge.py` beside its only consumer. It becomes a frozen `BaseModel`. Its
fields are `ctx`, `message`, `target`, `arguments`, `members`, `read`, `render`
and `failed`, each with a description; the callable fields use the existing `MemberRead` and `ReadFailure` aliases.

`method` becomes a property returning `self.message.method or ""`, so it can never disagree with the message. The two
construction sites pass `ctx=` and `message=` as keywords.

*Adjusted during implementation:* the plan named the `arbitrary_types_allowed` config, but every field already has a
validator. `RequestContext`, `JsonRpcMessage` and `McpServer` are models and the three callables validate as
callables, so the model builds without it. The repo rule reserves that config for runtime objects Pydantic cannot
validate, so `BridgedRead` uses the frozen recipe alone.

## Risks / Trade-offs

- **[Risk]** The concurrent fan-out puts more simultaneous load on the leases. Several members' sessions are now
  checked out at once, and the pool has no concurrent-lease test (audit S11). → **Mitigation:** each member has its
  own pool key, so no two coroutines contend for one pooled session. The BND-38 tests run two live members
  concurrently through the real pool. S11's own change owns pool concurrency in general.
- **[Risk]** A session-era list could now receive upstream requests for client input from two members at once on the
  GET stream. → **Mitigation:** the relay already serves concurrent tool calls in one session, and list methods
  rarely ask for input. No new path exists; only the timing differs.
- **[Risk]** Concurrent credential resolution: two members with upstream OAuth may refresh tokens at the same moment.
  → **Mitigation:** the refresh lock is per server and user (`REFRESH_LOCK_KEY` in the refresher), and different
  members are different servers.
- **[Risk]** `disconnected(admitted)` after `_release` now sets the event of a handle that is no longer registered.
  Before this change the handle attribute was cleared, so that call did nothing. → **Mitigation:** the event is only
  awaited while the upstream call runs, and release happens after the upstream call has returned. Setting it then is
  unobservable. The existing PROT-3 cancellation tests and the MRTR passthrough tests cover both sides of that window.
- **[Risk]** Deleting `attach` and changing the renderer signatures could break a caller outside `tool_call/`.
  → **Mitigation:** `grep -rn "\.attach(\|CallResponse(" packages/bundlemcp` finds only `tool_call.py:188-189`
  and `call_response.py:93`, and `ResumedCall` goes through `ToolCall.run()`.
- **[Trade-off]** Without a per-member bound, the worst-case list latency stays the same: one hanging member still
  holds the list. Only the typical case improves.

## Migration Plan

None. No stored data, wire format or setting changes. Request states sealed before the deploy keep their `mode`
strings and unseal unchanged. A rollback is a plain redeploy.
