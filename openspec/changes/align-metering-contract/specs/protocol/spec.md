## MODIFIED Requirements

### Requirement: PROT-24 Metering context
Every stage of the chain (PROT-25), the metering hook included, SHALL receive for every request it handles a context
carrying: the resolved caller identity (`sub` — a user id, `api_key:<id>`, or `None` when anonymous — and `email`; for
an OAuth user also the IdP's `oidc_issuer` and `oidc_sub`, which are `None` for API-key and anonymous callers); the auth
method (`oauth`, `api_key` or `none`); the endpoint, its bundle and its profile; the session id (`None` for a modern-era
request, which has no session); for calls the origin server, the original (unprefixed) tool name and the invocation's
`idempotency_key`; the request headers, read-only and without any credential-bearing header (`authorization`, `cookie`,
`proxy-authorization`, API-key headers); and a scratch mapping for data one stage leaves for a later one, which the
metering hook's `post_call` receives as its `pre_call` left it.

#### Scenario: OAuth caller's IdP subject reaches the hook
- **WHEN** a user signed in through the OIDC provider calls a tool over an OAuth endpoint
- **THEN** the hook's context carries that user's `oidc_issuer` and `oidc_sub` beside the gateway's own `sub`

#### Scenario: API-key caller
- **WHEN** a caller authenticated with an API key calls a tool
- **THEN** the context's `sub` is `api_key:<id>`, its auth method is `api_key`, and `oidc_issuer` and `oidc_sub` are
  `None`

#### Scenario: Profile and session reach the hook
- **WHEN** a handshake-era client calls a tool on an endpoint with profile `chatgpt`
- **THEN** the context carries profile `chatgpt` and the client's session id

#### Scenario: Headers without credentials
- **WHEN** a client calls a tool sending `authorization`, `user-agent` and `x-request-source` headers
- **THEN** the context's headers include `user-agent` and `x-request-source` and do not include `authorization`

#### Scenario: Scratch carries from pre-call to post-call
- **WHEN** the hook's `pre_call` stores a reservation id in the scratch mapping and allows the call
- **THEN** the same invocation's `post_call` receives that reservation id
- **AND** for the out-of-process hook the decision's `scratch` object is echoed in the `post_call` event

### Requirement: PROT-25 Built-in pipeline order
Every `tools/list` and `tools/call` SHALL pass through an ordered chain of stages, each receiving the PROT-24 context,
in this order (list and call variants):

1. tool filter — drops disabled tools / rejects disabled calls ([BND-13](../bundles/spec.md))
2. profile transform ([EP-13](../endpoints/spec.md))
3. overrides — apply/reverse per-bundle overrides ([BND-14](../bundles/spec.md)), after the profile, so
   an explicit annotation override wins over the profile's rewrite ([BND-15](../bundles/spec.md))
4. **metering hook** (calls only; no-op unless configured)
5. audit ([operations](../operations/spec.md))

A stage that rejects a call ends it; the audit stage still records the rejection. The chain and its order are
bundlemcp's contract regardless of the underlying library.

#### Scenario: Disabled tool never reaches metering
- **WHEN** a client calls a tool that is disabled in the bundle
- **THEN** the call is rejected without a `pre_call` to the metering hook and an audit record with status `denied` is
  written

#### Scenario: Allowed call is metered then audited
- **WHEN** a client calls an enabled tool and the hook allows it
- **THEN** `pre_call` fires before the upstream call, `post_call` after it, and one audit record with status `success`
  is written

#### Scenario: List passes the same stages
- **WHEN** a client lists tools on an endpoint whose bundle disables one tool and overrides another's name, with
  profile `chatgpt`
- **THEN** the disabled tool is absent, the overridden name is listed, and the profile's annotations apply to the
  overridden tool under its new name

### Requirement: PROT-26 Metering hook contract
The metering hook contract (mirroring the first consumer's existing billing API) SHALL be:

- **pre-call**: hook receives `{sub, email, oidc_issuer, oidc_sub, endpoint, bundle, server, tool, idempotency_key}`
  and the rest of the PROT-24 context (`email` nullable — the resolved caller's email, which the consumer's ledger uses
  to attach users; `oidc_issuer` / `oidc_sub` nullable — the IdP subject of an OAuth user, the same for every login of
  that user, for a consumer that keys its users on it; `sub` keeps its meaning). It may **allow** or **deny**; the
  upstream call never happens after a deny. A deny with a `user_message` answers the call with a tool result
  `isError: true` whose only content is that text verbatim, so the model relays it to the person; a deny without one
  answers a structured MCP error carrying the hook's `reason`, e.g. `insufficient_credits`.
- **post-call**: hook receives the same identifiers + an `outcome` + `duration_ms`. The outcome is `result` (a tool
  result), `tool_error` (a tool result with `isError: true`: the tool ran), `no_result` (unreachable or timed-out
  upstream, a JSON-RPC error, the gateway refusing the call after pre-call allowed it, or an invocation abandoned while
  waiting for client input) or `cancelled`. The gateway does not decide what an outcome costs; the hook does, and a
  debit followed by anything but `result` is its refund trigger to weigh.
- **Unanswered pre-call:** when pre-call raises instead of deciding and the failure policy denies the call, the
  gateway delivers a post-call `no_result` with `duration_ms` 0 for the same `idempotency_key`, since the hook may
  have debited before it failed to answer. Under fail-open the call proceeds and ends with an ordinary post-call.
- **Idempotency across retries:** pre-call fires **once per client invocation**. One `idempotency_key` is minted per
  client invocation; gateway-internal retries ([SES-7](../sessions/spec.md),
  [UPS-28](../upstreams/spec.md)) reuse it and do NOT re-fire pre-call. A call that spans several
  requests through Multi Round-Trip Requests ([PROT-18](../protocol/spec.md)) keeps the key
  sealed in its `requestState`, and none of its later legs — a parked call resumed in place, a pass-through retry or a
  re-run — fires pre-call again. Exactly one post-call is delivered per invocation that had a successful or an
  unanswered pre-call: on its final outcome, or with outcome `no_result` once an invocation paused for client input is
  not retried before its `requestState` expires. A leg that ends in `input_required` delivers none.
- **Crash reconciliation:** if the gateway dies between pre-call and post-call, no refund fires. The audit log
  ([operations](../operations/spec.md)) is the reconciliation source: hook consumers can detect debits
  with no completed audit record and refund out-of-band. This contract is part of the hook documentation.
- Field mapping to the reference consumer's `MeterRequest`: `sub→sub`, `email→email`, `bundle→bundle_slug`,
  `server→server_name`, `tool→tool_name`, `idempotency_key→idempotency_key`; `endpoint` is bundlemcp-side context the
  reference consumer ignores.
- Configured as a Python import path (`BUNDLEMCP_METERING_HOOK`); hook errors follow a configurable policy
  (`BUNDLEMCP_METERING_HOOK_FAIL_OPEN`): fail-open (log, allow) or fail-closed (deny) — default fail-closed.

#### Scenario: Allowed call reports its outcome
- **WHEN** the hook allows a call and the upstream returns a tool result
- **THEN** `post_call` receives outcome `result` and a `duration_ms` under the same `idempotency_key`

#### Scenario: Tool error result
- **WHEN** the upstream returns a result with `isError: true`
- **THEN** `post_call` receives outcome `tool_error`

#### Scenario: Deny with a user message
- **WHEN** the hook denies a call with `user_message` "Your credits are used up"
- **THEN** the client receives a tool result with `isError: true` whose only content is that text
- **AND** the upstream is not called

#### Scenario: Deny without a user message
- **WHEN** the hook denies a call with reason `insufficient_credits` and no `user_message`
- **THEN** the client receives a JSON-RPC error carrying `insufficient_credits` and the upstream is not called

#### Scenario: Pre-call raises under fail-closed
- **WHEN** `pre_call` raises and the fail-open setting is off
- **THEN** the call is denied without reaching the upstream
- **AND** `post_call` is delivered with outcome `no_result` and `duration_ms` 0 under the same key

#### Scenario: Reactive OAuth retry is charged once
- **WHEN** an upstream-OAuth call is retried once after an upstream 401
- **THEN** `pre_call` fired once and `post_call` fires once, with one `idempotency_key`

#### Scenario: MRTR retry is charged once
- **WHEN** a modern client's call returns `input_required` and the client's retry completes it, by pass-through or by
  re-run
- **THEN** `pre_call` fired once, on the first leg, and `post_call` fires once with the final outcome, under one
  `idempotency_key`

#### Scenario: Abandoned invocation
- **WHEN** a call returns `input_required` and the client never retries
- **THEN** after the `requestState` has expired `post_call` is delivered once with outcome `no_result` under the
  invocation's `idempotency_key`

### Requirement: PROT-18 Multi Round-Trip Requests
When an upstream needs client input during `tools/call`, `prompts/get` or `resources/read` for a modern client, the
gateway SHALL answer `resultType: "input_required"` with `inputRequests` and a sealed `requestState`; the client retries
the same method with `inputResponses` and the state, and any replica MUST be able to serve the retry. Two strategies,
chosen per upstream era:

- **Pass-through** (modern upstream): the upstream's own `InputRequiredResult` is forwarded — `inputRequests`
  verbatim, its `requestState` sealed inside the gateway's — and the retry re-issues the request upstream with the
  client's `inputResponses` and the upstream's state. No gateway state exists between the two requests beyond the
  metering record of a paused tool call ([PROT-26](../protocol/spec.md)).
- **Park and resume** (handshake upstream): the upstream's server-initiated request is turned into `inputRequests`;
  the in-flight upstream request stays parked on its reply future, bounded by PROT-6; the retry routes the answer to the
  parking replica over the signal bus and the result back to the replica serving the retry. If no replica claims the
  retry (the parking replica is gone), the request is **re-run** with the requests answered from `inputResponses` as
  they recur, so the client still gets a result; this fallback may repeat the upstream's side effects before the
  elicitation and is logged as such.

`requestState` is integrity-protected with the gateway's token cipher and binds the principal, the method and its
target (the presented tool and argument digest, the presented prompt name and argument digest, or the resource URI),
for `tools/call` the metering idempotency key, and an expiry; a state that fails verification, belongs to another
caller, another method or another target, or has expired is rejected with `-32602`. Only `tools/call` is metered: an
invocation's first leg fires `pre_call` once, its later legs — a parked call resumed in place, a pass-through retry, a
re-run — share the sealed idempotency key and do not fire it again, and `post_call` fires once when the invocation
ends, or with outcome `no_result` when it is not retried before its state expires (PROT-26). Only requests the client
declared support for in `_meta` capabilities are placed in `inputRequests` (PROT-5). Without token encryption keys the
bridge is unavailable and reports so with an error rather than sealing plaintext.

#### Scenario: Pass-through
- **WHEN** a modern upstream answers `input_required` to a modern client's call
- **THEN** the client receives `resultType: "input_required"` with the upstream's `inputRequests` and a sealed state
  that does not contain the upstream's state in clear
- **AND** the retry with `inputResponses` completes with `resultType: "complete"`, one `pre_call` and one `post_call`
  outcome `result`

#### Scenario: Park and resume on another replica
- **WHEN** a handshake upstream elicits during a modern client's call on replica A and the retry reaches replica B
- **THEN** the answer is routed to A and B streams the call's result

#### Scenario: Tampered or foreign state
- **WHEN** a retry carries a `requestState` that was altered, or was sealed for another caller or tool
- **THEN** the gateway answers HTTP 400 with `-32602`

#### Scenario: No encryption keys
- **WHEN** the gateway has no token encryption keys and an upstream asks for input during a modern client's call
- **THEN** the client receives an error saying `input_required` is unavailable

#### Scenario: Prompt needs input from a modern upstream
- **WHEN** a modern member answers `input_required` to a modern client's `prompts/get`
- **THEN** the client receives `resultType: "input_required"` with the member's `inputRequests`
- **AND** the retry with `inputResponses` returns the prompt with `resultType: "complete"`, and the metering hook is
  not called

#### Scenario: Resource read needs input from a handshake upstream
- **WHEN** a handshake member elicits during a modern client's `resources/read`
- **THEN** the client receives `input_required`, and its retry with the answer returns the resource contents

#### Scenario: State sealed for another method
- **WHEN** a client retries `resources/read` with a `requestState` sealed for a `prompts/get`
- **THEN** the gateway answers HTTP 400 with `-32602`
