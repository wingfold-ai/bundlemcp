# ADR-0007: Endpoint profiles; ChatGPT via annotation re-writing

**Status:** accepted · **Date:** 2026-07-02

## Context

Different MCP clients impose different constraints: claude.ai wants OAuth
with dynamic client registration; ChatGPT restricts/behaves differently
toward write tools. metamcp bound one endpoint to one namespace with auth
toggles only — no per-client shaping, so one bundle couldn't serve both
clients well.

## Decision

A bundle can have **many endpoints**, each with a built-in **profile**
([spec/14](../../spec/14-endpoints.md), [spec/15](../../spec/15-endpoint-profiles.md)):
`default` (passthrough), `claude` (OAuth-only, passthrough), `chatgpt`
(**re-annotates write tools as read-safe** — `readOnlyHint: true`,
`destructiveHint: false` — while the tools still perform their real
operations upstream). Profiles are code presets, not a plugin system.

## Reasons

- The user's explicit product requirement: same bundle, per-client surfaces.
- Re-annotation (rather than hiding writes) was chosen deliberately: expose
  everything, shaped to what the client accepts.
- Built-in presets keep v1 simple; PROF-5 leaves room for more profiles.

## Consequences

- (+) One bundle, N client-correct URLs; connection UX per client.
- (−) The chatgpt profile intentionally makes annotations lie about behavior;
  mitigated by a mandatory UI warning and normal audit logging (PROF-3).
- (−) Profile rules must track client behavior changes (open question in
  spec/15 to re-verify ChatGPT's enforcement at implementation time).
