# ADR-0005: Streamable HTTP only — no stdio, no SSE

**Status:** accepted · **Date:** 2026-07-02

## Context

metamcp supports STDIO (spawning npx/uvx processes inside the gateway), SSE, and Streamable HTTP — upstream and
downstream. STDIO was its largest complexity driver: process pools, crash tracking, env plumbing, a fat Node+Python
image. SSE is deprecated by the MCP spec. All targeted upstreams (the application layer's containers, hosted servers)
and clients (claude.ai, ChatGPT) speak Streamable HTTP.

## Decision drivers

- Removes the process-management subsystem entirely.
- Stateless-friendly transport aligns with the any-replica model (ADR-0004).
- Sidecars put stdio lifecycle where it belongs: the container platform.

## Decision

bundlemcp connects to upstreams and serves endpoints **exclusively over Streamable HTTP**
([spec/10](../../openspec/specs/upstreams/spec.md) UPS-1, [spec/14](../../openspec/specs/endpoints/spec.md)
EP-1). stdio servers are supported via a documented sidecar pattern (UPS-7), not in-process.

## Alternatives considered

_Not recorded at the time of the decision._

## Consequences

### Positive

- Slim image, drastically smaller connection-lifecycle surface.

### Trade-offs

- Users with stdio-only servers must run a sidecar (documented with a compose example,
  [spec/61](../../openspec/specs/documentation/spec.md)).
- Legacy SSE-only clients/servers are unsupported (recorded in the decision log).

