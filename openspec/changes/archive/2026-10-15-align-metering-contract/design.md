# Design: align the metering contract

## Context

See proposal.md for the motivation. Today:

- `MeterContext` (`application/metering/meter_context.py`, frozen) holds identity, endpoint, bundle, server, tool and
  `idempotency_key`. `CallerIdentity.auth_method` (`EndpointAuthMode`) and the endpoint's `EndpointProfile` exist in
  the domain but are not passed on. The HTTP hook (`infrastructure/metering/`) posts `context` as the dumped model.
- Since #107/#109 the stale filter, curation filter, profile and overrides are ordered domain stages
  (`domain/bundles/tool_pipeline.py`) applied when the bundle view is composed; metering and audit run inside
  `ToolCall` (`api/mcp/tool_call/tool_call.py`).
- `ToolCall` calls `_meter_pre_call` on every leg except a parked call resumed in place (`ResumedCall`); a leg ending in
  `input_required` writes an audit record with that status and skips `post_call`.
- `RequestState` (`api/mcp/relay/request_state.py`) binds `presented_tool`, an argument digest, `sub`, the
  `idempotency_key` and `expires_at`; only `ToolsCallHandler` produces and accepts it. `prompts/get` and
  `resources/read` go through `MemberFanout` with the relay but `raw_input_required` off.

## Goals / Non-Goals

**Goals:** the context the original contract promised; one `pre_call` and one `post_call` per invocation, abandoned
ones included; the MRTR bridge on every method the relay serves; no change for hooks that ignore the new fields.

**Non-Goals:** metering `tools/list`, `prompts/get` or `resources/read` (MID's open question stays open); a third-party
middleware plugin surface (MID out of scope); exactly-once delivery across a gateway crash (crash reconciliation stays
the audit log's job).

## Decisions

### D1. Context fields are additive; scratch is the one mutable field

`MeterContext` gains `auth_method`, `profile`, `session_id: str | None` (a real `None` for modern-era requests),
`headers: dict[str, str]` and `scratch: dict[str, Any]`. Headers are copied from the request with credential-bearing
names removed by a domain rule `CredentialHeaders` (`domain/access/credential_headers.py`, reusing the AUTH-28 deny-list
plus `cookie` and API-key headers), so no secret reaches a hook or the HTTP hook's network (spec 51). `scratch` is the
only mutable member of the frozen model; it is limited to 4 KiB of JSON so a hook cannot grow gateway state without
bound. The HTTP hook's decision schema gains an optional `scratch` object, echoed in the `post_call` event.

New optional fields do not break a structural `MeteringHook` or an HTTP consumer that ignores unknown keys, so
`METERING_PROTOCOL_VERSION` stays 2 (PROT-27).

### D2. One stage interface for list and call

A `ChainStage` contract (`application/serving/chain_stage.py`, `@runtime_checkable`) has four methods: `present(tool,
curation)` returns the tool as the stage shows it, or `None` to drop it (the list variant, and the served set a call is
resolved against); `admit(call)` runs before the upstream and may return a refusal; `pause(call, until)` says the leg
waits for client input; `settle(call, settlement)` runs after, with how the leg ended. A `ToolChain` (application,
frozen) holds the stages in PROT-25 order and runs each method across them: `present` stops at the first `None`,
`admit` at the first refusal, and `settle` reaches every stage so the audit stage records a refusal too. `pause` is
its own method rather than a kind of settlement because a parked call pauses while its leg goes on; only the metering
stage acts on it.

The built-ins: a `PresentationStage` wraps each domain tool stage from #107/#109 (`StaleToolFilter`, `CurationFilter`,
`ProfileStage`, `OverrideStage`) and implements only `present`; `MeteringStage` (the hook and the fail-open policy) and
`AuditStage` (the audit writer) act on calls. The bundle view loader presents tools through
`ToolChain.for_endpoint(profile)`, the same stage list without call stages; `ToolCall` admits, pauses and settles
through `ToolChain.for_endpoint(profile, call_stages)`. The domain `ToolPipeline` is replaced by the chain, and its
tests move with it. The call stages share one `ChainCall` (the `MeterContext`, the audit context, and whether a
post-call is owed), so the order of stages is the only coupling between them.

The three tool stages see the tool, its curation and the profile but not the caller: they run once while the served
tool set is built, before authentication. Presenting per caller (moving presentation out of the view) was considered
and rejected: no stage needs the caller, and it would re-present every tool on every request.

### D3. A paused-invocation record makes "once" enforceable

When a `tools/call` leg asks for input (pass-through or parked), the metering stage writes a `PausedInvocation`
(application model: the `MeterContext` including `scratch`, and the state's expiry) to Valkey under
`bmcp:invocation:{idempotency_key}`, and adds the key to the sorted set `bmcp:invocations:expiry`, through a new
`PausedInvocations` contract (`application/contracts/live_state/paused_invocations.py`). A retry whose sealed state
verifies **claims** the record atomically (`GETDEL`) and continues with the stored context: no `pre_call`. A further
`input_required` re-arms it with the new expiry. A parked call that resumes in place claims its own record before it
reports; if a re-run elsewhere or the sweeper claimed it first, it reports nothing.

An `InvocationSweeper` (application; `InvocationSweepJob` in `api/jobs/` runs it on one replica at a time under a
Valkey lease, every 30 s) claims records whose
expiry has passed and delivers `post_call` `no_result` for each. The claim is the same atomic operation, so a late retry
and the sweeper cannot both settle an invocation; the record lives a grace period longer than the state, and a retry
after the state expired is rejected by the state check anyway.

The sealed state already carries the `idempotency_key`, so the record adds no lookup the retry could not make, and a
record lost with a Valkey restart degrades to today's behaviour — the retry runs `pre_call` again (a logged
`metering.invocation_record_missing`), never a lost charge.

*Alternative, not taken:* the repeat as contract — no record, no sweeper, `METERING_PROTOCOL_VERSION` 3.

### D4. A bridge for the relayed reads

An `InputRequiredBridge` (`api/mcp/dispatch/handlers/input_required_bridge.py`, beside `MemberFanout`, which it
drives) serves a modern client's `prompts/get` and `resources/read`. It runs the member read detached and answers with
the first thing the read has for the client, as one JSON message: the result, or `input_required`. A modern member's
own `InputRequiredResult` is passed through (`allow_input_required=True` on the SDK's `get_prompt` and
`read_resource`) with its state sealed inside the gateway's and the member's name, so the retry goes back to it. A
handshake member's request for input goes through the same `ParkingChannel` tool calls use; the retry routes the
answers over the signal bus and answers with what the parked read says next, or re-runs the read with a
`PreansweredChannel` when no replica claims them. `MemberFanout.client_for` takes the channel.

`ToolCall` keeps its own driver, because it streams, meters and audits, and shares the relay pieces (`RequestState`,
the channels, `CallEvents`) with the bridge rather than the driver. `RequestState` gains `method` (default
`tools/call`), `target` (the presented tool or prompt name or the resource URI; read from `presented_tool` in a state
sealed before) and `member`, and its `idempotency_key` becomes optional (absent for reads); a state sealed by the
previous build still unseals. Reads are neither metered nor audited (ADR-0021).

### Layer summary

| Piece | Layer |
|---|---|
| `CredentialHeaders` | `domain/access/` |
| `MeterContext` fields, `ChainStage`, `ToolChain` and stages, `PausedInvocation`, `InvocationSweeper`, `PausedInvocations` contract | `application/` |
| Paused-invocation adapter and its in-memory fake | `infrastructure/valkey/`, `infrastructure/memory/` |
| `InputRequiredBridge`, `RequestState` fields, handlers, `InvocationSweepJob` | `api/mcp/`, `api/jobs/` |
| Sweeper start/stop, stage wiring | `main/` |

## Risks / Trade-offs

- [The hook can no longer deny the second leg of an invocation] → it decided once, on the first leg, with the same
  context; the documentation says so.
- [Headers in the context could leak something a deny-list misses, e.g. a custom token header] → the list is the AUTH-28
  deny-list plus the gateway's own credential headers, and the hook documentation tells operators that custom
  credential headers must be added to the forwarding deny-list.
- [The sweeper's `no_result` may race a retry that arrives just at expiry] → atomic claim; whichever claims first
  settles, the other sees no record (the retry is then rejected by its expired state).
- [Hooks that relied on a second `pre_call` to re-check credit] → called out in the hook documentation's changelog;
  the idempotency key is unchanged, so an idempotent hook sees no difference except one call fewer.

## Migration Plan

No database migration. Deploy order does not matter: an old replica serving a retry runs `pre_call` again (today's
behaviour); a new replica that finds no record does the same. The paused-invocation keys expire on their own if the
change is rolled back.
