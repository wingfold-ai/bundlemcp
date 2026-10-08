# ADR-0002: FastMCP v3 as the MCP framework

**Status:** superseded by [ADR-0030](0030-fastmcp-4.md) · **Date:** 2026-07-02

> **Do not follow this record.** The framework is FastMCP 4 on MCP SDK v2
> (`fastmcp>=4.0.3`), decided in [ADR-0030](0030-fastmcp-4.md). The version
> pin below is historical. What survives is the *shape* of the choice — a
> high-level framework for upstream clients, the low-level SDK where
> externalized session state demands it — which ADR-0030 kept.

## Context

The gateway must act as MCP client (to upstreams) and MCP server (per endpoint), with proxying, composition, and
per-call middleware. Options: the official low-level `mcp` python-sdk, FastMCP (v3 current), or a hybrid.

## Decision drivers

- Built-in proxying, server composition, and middleware hooks map directly onto bundles and the middleware chain
  ([spec/31](../../spec/31-middleware.md)).
- Latest-stable policy (ARC-1) favors the actively developed major version.

## Decision

FastMCP v3 (≥3.4) is the base framework; drop to the low-level SDK only where externalized session state
([spec/30](../../spec/30-session-management.md)) or bidirectional relaying
([spec/32](../../spec/32-protocol-passthrough.md)) demands it.

## Alternatives considered

_Not recorded at the time of the decision._

## Consequences

### Positive

- Large amount of transport/protocol plumbing not owned by us.

### Trade-offs

- The Redis-backed session model may fight framework assumptions; an implementation spike must establish the boundary
  (open questions in specs 30/32).
- Major-version framework churn is absorbed by us (mitigated by the spec layer being framework-agnostic).

