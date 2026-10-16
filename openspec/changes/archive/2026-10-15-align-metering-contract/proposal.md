# Proposal: align the metering contract

## Why

The metering hook is the one extension point the application layer builds billing on, and three parts of its contract
differ from what the gateway does:

- **Context (PROT-24).** The original contract gives every stage the auth method, the endpoint's profile, the session
  id, the request headers (read-only) and a scratch dict shared across stages. `MeterContext`
  (`application/metering/meter_context.py`) carries none of them, so a consumer cannot, for example, price an OAuth call
  differently from an API-key call or carry a reservation id from `pre_call` to `post_call`.
- **Chain (PROT-25).** The original contract is an ordered middleware chain for `tools/list` and `tools/call`. What
  exists is a fixed pipeline: curation, overrides and profile are applied when the bundle view is composed, metering and
  audit inside `ToolCall`. The order holds; the chain does not.
- **Once per invocation (PROT-26).** The original says `pre_call` fires once per client invocation. Today an MRTR
  pass-through retry and a re-run fire it again with the same key (`packages/bundlemcp/tests/api/test_mrtr.py` asserts
  two `pre_call`s), and a leg that ends in `input_required` gets no `post_call` — an invocation the client abandons
  never gets one, leaving a debit with no refund trigger. `docs/integrate/metering-hook.md` documents the repeat.

MRTR bridging also stops at `tools/call` for modern clients: on `prompts/get` and `resources/read` a handshake
upstream's request for input fails fast and a modern upstream's `input_required` is reported as an error (PROT-18).

## What Changes

- The metering context also carries the auth method, the endpoint's profile, the session id, the request headers
  read-only (credential headers removed) and a scratch mapping that `pre_call` fills and `post_call` receives (PROT-24).
- `tools/list` and `tools/call` run through one ordered chain of stages (PROT-25); its call stages receive that context.
- `pre_call` fires once per client invocation, MRTR legs included; an invocation abandoned after `input_required`
  receives a `post_call` `no_result` when its state expires (PROT-26).
- MRTR pass-through and park-and-resume extend to `prompts/get` and `resources/read` for modern clients; the metering
  sentence matches PROT-26 (PROT-18).

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `protocol`: MODIFIED PROT-24 (fuller context), PROT-25 (a chain of stages), PROT-26 (once per invocation, abandoned
  invocations get a post-call).
- `protocol`: MODIFIED PROT-18 (bridging for `prompts/get` and `resources/read`; metering sentence).

## Decisions

Settled by the maintainers on 2026-10-15:

- **PROT-25: build the chain, over today's split.** One `ChainStage` interface and one ordered `ToolChain` (tool
  filter, profile, overrides, metering, audit) that `tools/list` and `tools/call` both go through. The three tool
  stages keep running where the served tool set is built, since they depend only on the tool, its curation and the
  endpoint's profile; metering and audit run per call and receive the full PROT-24 context. Presenting tools per caller
  was considered and not built: it would re-present every tool on every request for no current consumer.
- **PROT-26: enforce once per invocation.** A short-lived Valkey record per paused invocation lets a retry skip
  `pre_call` and lets a sweeper close an abandoned invocation with `post_call` `no_result`. `METERING_PROTOCOL_VERSION`
  stays 2.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `protocol`: MODIFIED PROT-24 (fuller context), PROT-25 (a chain of stages), PROT-26 (once per invocation, abandoned
  invocations get a post-call).
- `protocol`: MODIFIED PROT-18 (bridging for `prompts/get` and `resources/read`; metering sentence).

## Open decision

- **PROT-25: build the chain or amend the spec.** Building it means one stage interface that list and call both pass
  through, each stage seeing the PROT-24 context. The alternative is to amend PROT-25 to the fixed pipeline that exists
  (curation, overrides and profile at view composition; metering and audit per call) and to drop the "scratch dict for
  cross-middleware data" from PROT-24, keeping a scratch only between `pre_call` and `post_call`. Decide together with
  [add-profile-interface](../archive/2026-10-13-add-profile-interface/proposal.md), whose EP-13 and BND-13 ask the same
  question for the profile and filter stages. The delta specifies the chain.
- **PROT-26: enforce once-per-invocation or make the repeat the contract.** Enforcing it needs a short-lived Valkey
  record per paused invocation (so a retry is recognised and an abandoned invocation can be closed with a `post_call`),
  and takes away the hook's chance to deny a later leg. Making "the same idempotency key, possibly repeated" the
  contract keeps today's behaviour, but is a contract change: `METERING_PROTOCOL_VERSION` goes to 3, and PROT-27 (not in
  this delta) must be modified with it. The delta specifies enforcement.

## Impact

- **Code:** `MeterContext` and the HTTP hook's event bodies gain fields (`application/metering/`,
  `infrastructure/metering/`); a chain-stage contract in `application/` with the built-in stages, run by the
  `tools/list` handler and `ToolCall` (`api/mcp/`); a paused-invocation record (contract in
  `application/contracts/live_state/`, Valkey adapter) and its expiry sweep; `ToolCall`/`ResumedCall` skip `pre_call`
  on later legs; the MRTR bridge generalised from `ToolsCallHandler` to the prompts-get and resources-read handlers,
  with the sealed `requestState` binding the method and target.
- **Contract:** additive context fields keep `METERING_PROTOCOL_VERSION` at 2 under the delta as written; the
  alternative PROT-26 outcome bumps it to 3.
- **Tests:** `packages/bundlemcp/tests/api/test_mrtr.py` changes its assertion to one `pre_call` per invocation.
- **Docs:** `docs/integrate/metering-hook.md` ("`pre_call` can fire more than once", "Calls that pause for input", the
  context table, the HTTP event bodies); arc42 §8; an ADR (next free number in `docs/adr/`) for the chain and the
  paused-invocation record, amending [ADR-0042](../../../docs/adr/0042-http-metering-hook-and-outcome-kinds.md).
- **Related changes:** [harden-audit-log](../2026-10-16-harden-audit-log/proposal.md) records the idempotency key on
  audit records (OPS-7); the paused-invocation record uses the same key.
  [add-upstream-session-pooling](../2026-10-16-add-upstream-session-pooling/proposal.md)'s SES-7 retry already reuses
  the key without a second `pre_call`.
