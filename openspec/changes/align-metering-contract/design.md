# Design: align the metering contract

## Context

See proposal.md for the motivation. Today:

- `MeterContext` (`application/metering/meter_context.py`, frozen) holds identity, endpoint, bundle, server, tool and
  `idempotency_key`. `CallerIdentity.auth_method` (`EndpointAuthMode`) and the endpoint's `EndpointProfile` exist in
  the domain but are not passed on. The HTTP hook (`infrastructure/metering/`) posts `context` as the dumped model.
- Curation, overrides and the profile transform are applied when the bundle view is composed
  (`domain/bundles/tool_presentation.py`); metering and audit run inside `ToolCall` (`api/mcp/tool_call/tool_call.py`).
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

A `ChainStage` contract (`application/serving/chain_stage.py`) with `on_list(ctx, tools)` and `on_call(ctx, call)`; the
built-ins wrap the existing domain rules: `ToolFilterStage`, `OverridesStage`, `ProfileStage` (list and call),
`MeteringStage`, `AuditStage` (call only). A `ToolChain` (application) runs them in the PROT-25 order, short-circuiting
on a rejection while still running the audit stage. The `tools/list` handler and `ToolCall` call the chain instead of
composing the steps themselves, so each stage sees the PROT-24 context. The domain functions stay where they are; the
stages only sequence them.

*Alternatives:* FastMCP middleware — the client-facing edge is not FastMCP (ADR-0011); amending the spec to the fixed
pipeline (the Open decision). Whatever is chosen should match add-profile-interface's EP-13 decision: if that change
builds a pluggable profile stage, it is `ProfileStage` here.

### D3. A paused-invocation record makes "once" enforceable

When a `tools/call` leg ends in `input_required`, `ToolCall` writes a `PausedInvocation` (application model: the
`MeterContext` including `scratch`, the leg's start time, the state's expiry) to Valkey under
`bmcp:invocation:{idempotency_key}`, and adds the key to the sorted set `bmcp:invocations:expiry`, through a new
`PausedInvocations` contract (`application/contracts/live_state/paused_invocations.py`). A retry whose sealed state
verifies **claims** the record atomically (check-and-set, as SES-1a does for sessions) and continues with the stored
context: no `pre_call`. A further `input_required` re-arms it with the new expiry; a final outcome deletes it and
delivers the one `post_call`.

An `InvocationSweeper` (application, one replica at a time under a Valkey lease, every 30 s) claims records whose
expiry has passed and delivers `post_call` `no_result` for each. The claim is the same atomic operation, so a late retry
and the sweeper cannot both settle an invocation; the record lives a grace period longer than the state, and a retry
after the state expired is rejected by the state check anyway.

The sealed state already carries the `idempotency_key`, so the record adds no lookup the retry could not make, and a
record lost with a Valkey restart degrades to today's behaviour — the retry runs `pre_call` again (a logged
`metering.invocation_record_missing`), never a lost charge.

*Alternative:* the repeat as contract (Open decision) — no record, no sweeper, `METERING_PROTOCOL_VERSION` 3.

### D4. One bridge for every relayed method

The MRTR logic leaves `ToolCall` for an `InputRequiredBridge` (`api/mcp/relay/input_required_bridge.py`) that takes
the upstream request as a callable and returns either a final result or an `input_required` result. `ToolCall`, the
prompts-get handler and the resources-read handler use it; `MemberFanout` gains the raw-`input_required` path
`UpstreamCall` has today. `RequestState` gains `method` (default `tools/call`) and `target` fields, and its
`idempotency_key` becomes optional (absent for reads); defaults keep states sealed by the previous build valid during a
rollout. Reads are neither metered nor audited (ADR-0021), so the bridge takes the metering and audit callbacks as
optional collaborators.

### Layer summary

| Piece | Layer |
|---|---|
| `CredentialHeaders` | `domain/access/` |
| `MeterContext` fields, `ChainStage`, `ToolChain` and stages, `PausedInvocation`, `InvocationSweeper`, `PausedInvocations` contract | `application/` |
| Paused-invocation adapter and lease; HTTP hook `scratch` | `infrastructure/valkey/`, `infrastructure/metering/` |
| `InputRequiredBridge`, `RequestState` fields, handlers | `api/mcp/` |
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
