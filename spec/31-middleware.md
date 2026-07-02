# 31 — Middleware chain & metering hook

**Status:** Accepted · **Origin:** improvement (metamcp had the chain; the metering hook was only a code comment)
**Prior art:** `../metamcp/apps/backend/src/lib/metamcp/metamcp-middleware/functional-middleware.ts`, `../ultra-mcp/packages/billing/ultra_billing/routers/meter.py` (the consumer contract)

## Summary

Every `tools/list` and `tools/call` passes through an ordered middleware
chain. Built-ins implement bundle curation, profiles, and auditing; a
documented **metering hook** is the supported extension point where an
application layer (ultra-mcp) plugs billing in **without forking bundlemcp**.

## Requirements

- **MID-1** Context object available to every middleware: resolved caller
  identity (`sub` / api-key id, auth method), endpoint, bundle, profile,
  session id, origin server + original tool name (for calls), request
  headers (read-only), and a scratch dict for cross-middleware data.
- **MID-2** Built-in chain order (list and call variants):
  1. tool filter — drops disabled tools / rejects disabled calls
     ([TM-2](13-tool-management.md))
  2. overrides — apply/reverse per-bundle overrides ([TM-3](13-tool-management.md))
  3. profile transform ([PROF-4](15-endpoint-profiles.md))
  4. **metering hook** (calls only; no-op unless configured)
  5. audit ([50-audit-log.md](50-audit-log.md))
  Built on FastMCP v3's middleware mechanism where it fits; the chain and
  ordering are bundlemcp's contract regardless of the underlying library.
- **MID-3 Metering hook contract** (mirrors ultra-mcp's existing billing API):
  - **pre-call**: hook receives `{sub, endpoint, bundle, server, tool,
    idempotency_key}` (idempotency key unique per invocation, stable across
    internal retries). It may **allow** or **deny** (deny → structured MCP
    error with the hook's reason, e.g. `insufficient_credits`; the upstream
    call never happens).
  - **post-call**: hook receives the same identifiers + `status`
    (success/error) + `duration_ms`. A failed upstream call after a
    successful pre-call debit is the hook's refund trigger.
  - Configured as a Python entry-point/import path
    (`BUNDLEMCP_METERING_HOOK`); hook errors follow a configurable policy:
    `fail-open` (log, allow) or `fail-closed` (deny) — default fail-closed.
- **MID-4** The hook interface is a **stable, versioned, documented** Python
  protocol (ABC) — semver-relevant: breaking it is a major version.
- **MID-5** Middleware MUST NOT swallow errors silently; every deny/error path
  produces a structured MCP error to the client and an audit record.

## Out of scope

- A general plugin marketplace or dynamic loading of arbitrary third-party
  middleware; one configured hook + built-ins is the v1 surface.
- The billing logic itself (ledger, pricing, refunds) — application layer.

## Open questions

- Whether the hook should also see `tools/list` (e.g. to hide tools a user
  has no entitlement for) — deferred; ultra-mcp's current model gates at
  call time.
