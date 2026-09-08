# ADR-0001: Rewrite metamcp's bundling core, don't fork it

**Status:** accepted · **Date:** 2026-07-02

## Context

metamcp proved the product shape (servers → namespaces → endpoints) but is
barely maintained (last release 2025-12; the author announced development will
stay slow). Its architecture keeps all live state — connection pools,
transports, rate-limit counters — in the memory of one Node process, causing
production `404 Session not found` storms on every restart and making
horizontal scaling impossible. The maintainer of this repo already had to run
an unreleased branch with hand-picked fixes. The maintainer's home stack is
Python + Vue, not TypeScript + Next.js.

## Decision drivers

- The session-state flaw is architectural; fixing it upstream means rewriting
  metamcp's core in a codebase we don't want to own long-term.
- Maintenance risk: depending on a stalled upstream for a load-bearing
  gateway.
- Stack familiarity compounds: every future feature is cheaper in the home
  stack.
- A rewrite allows deliberate scope reduction (see the decision log in
  [spec/README](../../spec/README.md)).

## Decision

Build **bundlemcp**: a from-scratch rewrite of only the bundling core
(registry → bundles → endpoints), specified in `/spec`, in Python + Nuxt.
metamcp remains a read-only reference (prior-art citations in specs).

## Alternatives considered

_Not recorded at the time of the decision._

## Consequences

### Positive

- Restart-safe, horizontally scalable design from day one (ADR-0004).
- Clean, service-authenticated integration surface for ultra-mcp.

### Trade-offs

- Re-implementation effort for features metamcp already had; feature gap
  until parity on the kept subset.
- Migration from a running metamcp is manual for now (roadmap item).

