# 31 — Middleware chain & metering hook

**Status:** Accepted · **Origin:** improvement (metamcp had the chain; the metering hook was only a code comment)
**Prior art:** `../metamcp/apps/backend/src/lib/metamcp/metamcp-middleware/functional-middleware.ts`, the first
consumer's billing meter router (the consumer contract)

## Summary

Every `tools/list` and `tools/call` passes through an ordered middleware chain. Built-ins implement bundle curation,
profiles, and auditing; a documented **metering hook** is the supported extension point where an application layer plugs
billing in **without forking bundlemcp**.

## Requirements

- **MID-1** Context object available to every middleware: resolved caller identity (`sub` / api-key id, auth method, and
  for an OAuth user the IdP's `oidc_issuer` and `oidc_sub` — `None` for API-key and anonymous callers), endpoint,
  bundle, profile, session id, origin server + original tool name (for calls), request headers (read-only), and a
  scratch dict for cross-middleware data.
- **MID-2** Built-in chain order (list and call variants):
  1. tool filter — drops disabled tools / rejects disabled calls
     ([TM-2](13-tool-management.md))
  2. overrides — apply/reverse per-bundle overrides ([TM-3](13-tool-management.md))
  3. profile transform ([PROF-4](15-endpoint-profiles.md))
  4. **metering hook** (calls only; no-op unless configured)
  5. audit ([50-audit-log.md](50-audit-log.md))
  Built on FastMCP v3's middleware mechanism where it fits; the chain and ordering are bundlemcp's contract regardless
  of the underlying library.
- **MID-3 Metering hook contract** (mirrors the first consumer's existing billing API):
  - **pre-call**: hook receives `{sub, email, oidc_issuer, oidc_sub, endpoint, bundle, server, tool, idempotency_key}`
    (`email` nullable — the resolved caller's email, which the consumer's ledger uses to attach users; `oidc_issuer` /
    `oidc_sub` nullable — the IdP subject of an OAuth user, the same for every login of that user, for a consumer that
    keys its users on it; `sub` keeps its meaning). It may **allow** or **deny**; the upstream call never happens after
    a deny. A deny with a `user_message` answers the call with a tool result `isError: true` whose only content is that
    text verbatim, so the model relays it to the person; a deny without one answers a structured MCP error carrying the
    hook's `reason`, e.g. `insufficient_credits`.
  - **post-call**: hook receives the same identifiers + an `outcome` + `duration_ms`. The outcome is `result` (a tool
    result), `tool_error` (a tool result with `isError: true`: the tool ran), `no_result` (unreachable or timed-out
    upstream, a JSON-RPC error, or the gateway refusing the call after pre-call allowed it) or `cancelled`. The gateway
    does not decide what an outcome costs; the hook does, and a debit followed by anything but `result` is its refund
    trigger to weigh.
  - **Unanswered pre-call:** when pre-call raises instead of deciding and the failure policy denies the call, the
    gateway delivers a post-call `no_result` with `duration_ms` 0 for the same `idempotency_key`, since the hook may
    have debited before it failed to answer. Under fail-open the call proceeds and ends with an ordinary post-call.
  - **Idempotency across retries:** pre-call fires **once per client invocation**; gateway-internal retries
    ([SES-7](30-session-management.md), [UPO-4](23-upstream-oauth.md)) reuse the same `idempotency_key` and do NOT
    re-fire pre-call. Exactly one post-call is delivered per invocation that had a successful or an unanswered pre-call
    — on the final outcome.
  - **Crash reconciliation:** if the gateway dies between pre-call and post-call, no refund fires. The audit log
    ([50-audit-log.md](50-audit-log.md)) is the reconciliation source: hook consumers can detect debits with no
    completed audit record and refund out-of-band. This contract is part of the hook documentation.
  - Field mapping to the reference consumer's `MeterRequest`: `sub→sub`, `email→email`, `bundle→bundle_slug`,
    `server→server_name`, `tool→tool_name`, `idempotency_key→idempotency_key`; `endpoint` is bundlemcp-side context the
    reference consumer ignores.
  - Configured as a Python entry-point/import path (`BUNDLEMCP_METERING_HOOK`); hook errors follow a configurable
    policy: `fail-open` (log, allow) or `fail-closed` (deny) — default fail-closed.
- **MID-4** The hook interface is a **stable, versioned, documented** Python protocol (ABC) — semver-relevant: breaking
  it is a major version. Version 2 replaced the post-call `status` (`success`/`error`) with the `outcome` kind.
- **MID-5** Middleware MUST NOT swallow errors silently; every deny/error path produces a structured MCP error to the
  client and an audit record.
- **MID-6 HTTP metering hook.** A built-in hook reaches a billing service over HTTP, so a deployment running a pinned
  image needs no Python plugin: `BUNDLEMCP_METERING_HTTP_URL`, a bearer token from `BUNDLEMCP_METERING_HTTP_TOKEN`
  (never logged), and `BUNDLEMCP_METERING_HTTP_TIMEOUT` (default 2 s). It cannot be combined with
  `BUNDLEMCP_METERING_HOOK`; startup refuses both.
  - Every event is a JSON `POST` to that URL: `{protocol_version, event: "pre_call", context}` and
    `{protocol_version, event: "post_call", context, outcome, duration_ms}`, where `context` is the MID-3 context.
  - A pre-call answer is a 2xx JSON decision `{allowed, reason?, user_message?}`. A timeout, a transport error, a
    non-2xx status or a body that is not a decision is an unanswered pre-call (MID-3), decided by the failure policy.
  - A post-call is acknowledged by any 2xx. It is delivered in the background, so a tool result never waits for it, and
    retried on a transport error, a timeout, a 429 or a 5xx: five tries within about a minute, then logged as
    `metering.post_call_failed` with the `idempotency_key`. Any other answer is final. On shutdown, deliveries in flight
    get a few seconds to finish.

## Out of scope

- A general plugin marketplace or dynamic loading of arbitrary third-party middleware; one configured hook + built-ins
  is the v1 surface.
- The billing logic itself (ledger, pricing, refunds) — application layer.

## Open questions

- Whether the hook should also see `tools/list` (e.g. to hide tools a user has no entitlement for) — deferred; the
  reference consumer's current model gates at call time.
