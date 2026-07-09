# ADR-0005: Streamable HTTP only — no stdio, no SSE

**Status:** accepted · **Date:** 2026-07-02

## Context

metamcp supports STDIO (spawning npx/uvx processes inside the gateway), SSE,
and Streamable HTTP — upstream and downstream. STDIO was its largest
complexity driver: process pools, crash tracking, env plumbing, a fat
Node+Python image. SSE is deprecated by the MCP spec. All targeted upstreams
(ultra-mcp containers, hosted servers) and clients (claude.ai, ChatGPT) speak
Streamable HTTP.

## Decision

bundlemcp connects to upstreams and serves endpoints **exclusively over
Streamable HTTP** ([spec/10](../../spec/10-server-registry.md) SRV-1,
[spec/14](../../spec/14-endpoints.md) EP-1). stdio servers are supported via a
documented sidecar pattern (SRV-7), not in-process.

## Reasons

- Removes the process-management subsystem entirely.
- Stateless-friendly transport aligns with the any-replica model (ADR-0004).
- Sidecars put stdio lifecycle where it belongs: the container platform.

## Consequences

- (+) Slim image, drastically smaller connection-lifecycle surface.
- (−) Users with stdio-only servers must run a sidecar (documented with a
  compose example, [spec/61](../../spec/61-docs-and-onboarding.md)).
- (−) Legacy SSE-only clients/servers are unsupported (recorded in the
  decision log).
