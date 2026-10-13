# ADR-0007: Endpoint profiles; ChatGPT via annotation re-writing

**Status:** accepted · **Date:** 2026-07-02

## Context

Different MCP clients impose different constraints: claude.ai wants OAuth with dynamic client registration; ChatGPT
restricts/behaves differently toward write tools. metamcp bound one endpoint to one namespace with auth toggles only —
no per-client shaping, so one bundle couldn't serve both clients well.

## Decision drivers

- The user's explicit product requirement: same bundle, per-client surfaces.
- Re-annotation (rather than hiding writes) was chosen deliberately: expose everything, shaped to what the client
  accepts.
- Built-in presets keep v1 simple; EP-14 leaves room for more profiles.

## Decision

A bundle can have **many endpoints**, each with a built-in **profile**
([spec/14](../../openspec/specs/endpoints/spec.md), [spec/15](../../openspec/specs/endpoints/spec.md)):
`default` (passthrough), `claude` (OAuth-only, passthrough), `chatgpt` (**re-annotates write tools as read-safe** —
`readOnlyHint: true`, `destructiveHint: false` — while the tools still perform their real operations upstream). Profiles
are code presets, not a plugin system.

## Alternatives considered

_Not recorded at the time of the decision._

## Consequences

### Positive

- One bundle, N client-correct URLs; connection UX per client.

### Trade-offs

- The chatgpt profile intentionally makes annotations lie about behavior; mitigated by a mandatory UI warning and normal
  audit logging (EP-12).
- Profile rules must track client behavior changes (open question in spec/15 to re-verify ChatGPT's enforcement at
  implementation time).

