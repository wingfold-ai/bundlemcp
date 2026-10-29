# Proposal

## Why

The MCP edge relies on calls happening in the right order, and `assert` is what enforces that:

- `ToolCall` (`api/mcp/tool_call/tool_call.py`) starts with `_timeouts`, `_handle` and `_events` set to `None`. They
  are filled in later by `run()` and `attach()`, and four asserts (lines 296, 349, 363, 384) narrow them back to
  non-`None`. `_admitted_at` is first assigned inside `run()` (line 154).
- `_pause(mode: str)` passes a plain string into a `Literal` field, so it needs `# type: ignore[arg-type]` (line 367).
  The read bridge has the same problem (`input_required_bridge.py:155`).
- `RequestContext.session` is optional because a modern request has no session. Code that only runs for session-era
  requests narrows it with asserts anyway: `session_adapter.py:62,85` and `upstream_leases.py:162`.
  `upstream_leases.py:138` uses another assert to narrow `lease.binding`.

`python -O` strips all of these asserts, and each one then turns into an `AttributeError` partway through a request.
More important, the asserts hide the order of steps that the reader needs to see.

The member fan-out (`api/mcp/dispatch/handlers/member_fanout.py`) is inconsistent in two ways:

- `first()` (lines 191–196) catches every `Exception` and logs it without `exc_info`. `_ask()` already separates
  "unconnected" from "failed" and logs the traceback.
- `merged()` asks the members that have no shareable snapshot one after another, so a list takes the sum of their
  latencies. [ADR-0021](../../../docs/adr/0021-mcp-surface-completion.md) decided that "each request fans out
  concurrently to the enabled member servers". The code no longer does that.
- `each()` has no caller.

`BridgedRead` (`input_required_bridge.py:53`) is a plain class that only holds eight attributes. The repo rule is that
every structured value is a `BaseModel`.

The 2026-10-29 code audit reported these as findings S12, S17 and S21.

## What Changes

- **Tool call steps take the admitted call as a parameter.** `ToolCall.run()` builds a frozen `AdmittedCall` once the
  chain has admitted the call. It holds the forwarded headers, the credentials, the call timeouts and the call handle.
  `run()` hands it to the response renderer, and every later step takes it as a parameter. The streamed renderer passes
  its `CallEvents` directly to the steps that need them, so `attach()` and the `None`-initialised attributes go away.
  The start time `_refuse` reports becomes a parameter of `_refuse` instead of an attribute.
- **Session-era code gets a context type with a required session.** `SessionRequestContext` extends `RequestContext`
  and makes `session` required. `SessionMcpAdapter._admit_session` returns it, and `UpstreamLeases.end_session` takes
  it, so their asserts go away. `RequestContext.session` stays `SessionRecord | None`, because `None` is the real state
  of every modern request.
- **The relay mode is a named `Literal`.** `RelayMode = Literal["parked", "passthrough"]` sits beside `RequestState`.
  `RequestState.mode`, `ToolCall._pause` and the bridge's `seal` all use it, which removes both
  `# type: ignore[arg-type]`. The value sealed into a request state does not change.
- **No assert narrows a value at runtime** in the files above. `upstream_leases.py:138` uses a combined condition
  instead.
- **`MemberFanout.first()` reuses `_ask()`.** It still asks members one at a time in member order and stops at the
  first answer: this is BND-8's "first member that owns the URI wins", and it contacts no member after the owner.
- **`MemberFanout.merged()` asks its live members concurrently.** The answers are still combined in member order, so
  de-duplication and collision logging behave exactly as before. `each()` is deleted.
- **`BridgedRead` becomes a frozen `BaseModel`.** Every field has a description, and `method` becomes a property
  derived from the message.
- **Added requirement BND-38:** a list that has to ask several members live asks them concurrently. Its latency is set
  by its slowest member, not by the sum of all of them, and the result is unchanged by the order in which members
  answer.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `bundles`: adds BND-38 (concurrent live list fan-out, result in member order). BND-1 and BND-8 are unchanged. The
  merged list keeps member order and first-wins de-duplication, and `resources/read` keeps its member-order fan-out.

## Impact

- **Resolves:** audit findings S12, S17 and S21 (2026-10-29). No GitHub issue. This change also removes the missing
  `exc_info` at `member_fanout.py:194`, one of the six sites listed in S18; the other five are not covered here.
- **Code (api layer only):**
  - `api/mcp/tool_call/`: `tool_call.py`, `call_response.py`, and the new `admitted_call.py`
  - `api/mcp/protocol/`: `request_context.py` is unchanged; `session_request_context.py` is new
  - `api/mcp/routing/adapters/session_adapter.py`
  - `api/mcp/upstream/upstream_leases.py`
  - `api/mcp/relay/request_state.py`, plus `relay/__init__.py` to export `RelayMode`
  - `api/mcp/dispatch/handlers/`: `member_fanout.py`, `input_required_bridge.py`, and the two places that build
    `BridgedRead` (`prompts_get_handler.py` and `resources_read_handler.py`)
- **API:** none. No DTO or route changes, so the OpenAPI document is not regenerated.
- **Wire:** sealed request states keep their shape and their `mode` strings, so a state sealed before the deploy still
  unseals afterwards.
- **Upstreams:** a `prompts/list`, `resources/list` or `resources/templates/list` that needs several live members now
  has those members' requests in flight at the same time. Each member still receives exactly one request.
- **Docs:** none. No ADR is needed. Concurrent fan-out is what ADR-0021 already decided, and this change brings the code
  back into line with it. ADR-0043 (contact only capable members) is unaffected, because the same members are
  contacted.
