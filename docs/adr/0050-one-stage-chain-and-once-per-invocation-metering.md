# ADR-0050: Tools pass one stage chain, and an invocation is metered once

**Status:** accepted · **Date:** 2026-10-15 · **Amends:** [ADR-0042](0042-http-metering-hook-and-outcome-kinds.md),
[ADR-0046](0046-profiles-as-registered-presets-and-tool-pipeline-stages.md)

## Context

The protocol spec promised a pipeline in which every stage, metering included, sees one context, and a metering hook
called once per client invocation. The code had neither. The tool stages (stale filter, curation, profile, overrides)
were a domain pipeline applied when the bundle view is built; metering and audit were steps inside `ToolCall` with
their own inputs. The hook was told the caller and the tool, but not how the caller authenticated, the endpoint's
profile, the session or the request headers, and had nowhere to keep a reservation id between `pre_call` and
`post_call`.

A tool call that pauses for client input through Multi Round-Trip Requests (MRTR) spans several requests. Each retry
ran `pre_call` again under the same idempotency key, and an invocation the client never retried received no
`post_call` at all, so a hook that reserved credit on `pre_call` held it forever.

## Decision drivers

- One ordered list of stages, the same for listing and calling, that a test can assert.
- The hook decides once per invocation and always hears how it ended.
- No state a request depends on lives only in one replica's memory.
- Presenting tools stays as cheap as it is: once per view, not once per request.

## Decision

- **One `ChainStage` interface and one `ToolChain`** (`application/serving/`): `present` (the tool as the stage shows
  it, or `None`), `admit` (may refuse a call before the upstream), `pause` (the call waits for client input) and
  `settle` (how the call ended). The chain is
  stale filter, curation filter, profile, overrides, metering, audit. The first four wrap the domain stages and run
  while the bundle view is built, so a dropped tool is gone from both `tools/list` and `tools/call`; metering and
  audit act on calls. `settle` reaches every stage, so audit records a refusal too.
- **The call stages receive a richer `MeterContext`**: the auth method, the endpoint's profile, the session id
  (`None` for a modern request), the request headers without credential-bearing ones, and a `scratch` mapping that
  `pre_call` fills and `post_call` receives. The HTTP hook returns `scratch` in its decision and gets it back in the
  `post_call` event.
- **A paused invocation is a Valkey record.** A leg that ends in `input_required` stores the invocation's context under
  its idempotency key with the state's expiry. A retry claims the record atomically and continues without `pre_call`;
  a sweeper, one replica at a time under a lease, claims expired records and delivers `post_call` `no_result`. The same
  atomic claim means a late retry and the sweeper cannot both settle one invocation.
- **`METERING_PROTOCOL_VERSION` stays 2.** A hook that keys on the idempotency key sees one `pre_call` fewer and one
  `post_call` more, both of which the contract already promised.

## Alternatives considered

- **Present tools per caller**, moving the tool stages out of the bundle view into the chain run per request. No stage
  needs the caller, and every request would re-present every tool.
- **Make the repeated `pre_call` the contract** and bump the protocol version. No record and no sweeper, but every hook
  must deduplicate, and an abandoned invocation still never hears an outcome.
- **Keep the paused invocation in the sealed `requestState`.** The client holds that state, so nothing could notice an
  invocation the client abandoned.

## Consequences

### Positive

- The stage order is one list; a new call stage is one class.
- A hook can reserve on `pre_call` and settle on `post_call`, with the reservation id in `scratch`.

### Trade-offs

- The hook can no longer refuse a later leg of an invocation; it decided on the first.
- A paused invocation costs one Valkey record until it ends or expires. A record lost with a Valkey restart degrades to
  the earlier behaviour: the retry runs `pre_call` again, logged, never a lost charge.
- The `no_result` for an abandoned invocation arrives up to one sweep interval after its state expires.
