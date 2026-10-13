# ADR-0042: The metering hook can run out of process, and reports outcome kinds

**Status:** accepted · **Date:** 2026-10-08 · **Amends:** spec 31 (PROT-26, PROT-27)

## Context

The metering hook (spec 31) was an in-process Python object loaded from `BUNDLEMCP_METERING_HOOK`. A deployment that
runs the published gateway image unchanged, with its hook logic in a separate service, had to bake a Python plugin into
a custom image just to make an HTTP call, and every such plugin re-implemented timeouts and retries on its own.

The contract also decided on the hook's behalf what a call's ending means. `post_call` received
`status: success | error`, with an MCP result carrying `isError: true` mapped to `error` by fiat. That folds two
different facts into one: an upstream that returned `isError` did run, and may well be billable, while one that was
unreachable or timed out produced nothing.

Two further gaps showed up once the hook is a network call:

- A `pre_call` that times out or fails may already have acted on the call (debited, counted a quota) on the hook's side,
  but PROT-26 delivered a `post_call` only after a successful `pre_call`, so that debit was never compensated.
- The only text a denied caller saw was `reason`, a machine code, as a JSON-RPC error that clients rarely show to the
  person, who therefore never learned why the call was refused or what to do about it.

## Decision drivers

- A hook that runs as its own service needs no custom image and no Python code in the gateway.
- The gateway reports facts; the hook decides what they mean.
- A failed exchange with the hook must never leave a pre-call without a matching report, and must never delay a tool
  result.
- The extension point stays one hook per deployment, in-process or HTTP, behind one protocol.

## Decision

- **Built-in out-of-process hook.** `HttpMeteringHook` (`infrastructure/metering/`) implements `MeteringHook` by
  `POST`ing JSON events to `BUNDLEMCP_METERING_HTTP_URL`, with an optional bearer token and a per-pre-call timeout
  (default 2 s). The bodies are Pydantic models (`PreCallEvent`, `PostCallEvent`) carrying `protocol_version`, `event`,
  the `MeterContext` and, for post-call, `outcome` and `duration_ms`. A pre-call answer is a 2xx JSON `MeterDecision`,
  parsed strictly; anything else raises, so the gateway's existing failure policy decides the call. Setting both the
  HTTP URL and `BUNDLEMCP_METERING_HOOK` refuses startup.
- **Post-call delivery is the adapter's job.** The HTTP hook queues each post-call as a background task, retries on a
  transport error, a timeout, a 429 or a 5xx (five tries within about a minute), and drains in-flight deliveries for a
  few seconds on shutdown. The gateway keeps awaiting `post_call` inline, so in-process hooks behave as before.
- **Outcome kinds replace success/error.** `post_call(ctx, outcome: MeterOutcome, duration_ms)` with `result`,
  `tool_error`, `no_result` and `cancelled`. `CallOutcome.meter_outcome` is the one place the gateway classifies a
  call's ending. `METERING_PROTOCOL_VERSION` becomes 2: a breaking change under PROT-27.
- **Compensation is the gateway's job.** When `pre_call` raises and the failure policy denies the call, `ToolCall`
  delivers `post_call(no_result, 0)` under the same `idempotency_key`. Because it lives in the gateway, it applies to
  every hook, not just the HTTP one.
- **A user-facing denial.** `MeterDecision.user_message` is optional. A denial with one is answered as a tool result
  with `isError: true` and the text verbatim, which models relay to the person; a denial without one is the JSON-RPC
  error it was before.

## Alternatives considered

- **Keep status success/error and add `outcome` as an optional keyword**, passed only to hooks whose signature accepts
  it. Non-breaking, but it leaves two ways to say the same thing and a signature sniff in the loader for good.
- **Retry post-calls in the gateway for every hook.** It would make in-process hooks run detached from the response, a
  behaviour change for code that works today, and retry policy belongs with the transport that fails.
- **Separate URLs for pre-call and post-call.** One more setting for the operator to get wrong; the `event` field
  already discriminates.
- **Always answer a denial as a tool result.** Changes what every existing client receives for a hook that never set a
  message, and a JSON-RPC error is still the clearer signal for a programmatic caller.
- **A durable outbox for post-calls.** Survives a crash, but adds a persistent queue for a case the audit log already
  covers as the reconciliation source (PROT-26).

## Consequences

### Positive

- An out-of-process hook integrates with configuration alone, and the published image stays unmodified.
- The hook can treat `tool_error` and `no_result` differently.
- A pre-call that never answered is always followed by a `no_result` report.
- A denied person sees why, in the operator's words.

### Trade-offs

- Every in-process hook must change its `post_call` signature to move to version 2.
- A post-call still being retried when the gateway crashes is lost; reconciliation stays with the audit log, as before.
- A post-call can arrive more than once after a retry, so a hook service must treat it as idempotent on
  `idempotency_key`, as they already must for pre-call.
- The hook URL is operator configuration and does not pass the egress policy, like the database and Valkey URLs.
