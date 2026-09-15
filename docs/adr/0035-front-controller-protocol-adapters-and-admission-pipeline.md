# ADR-0035: Front Controller, Protocol Adapters (Stateless vs. Session), and Admission Pipeline at the MCP Edge

**Status:** accepted · **Date:** 2026-09-15 · **Amends:** [ADR-0011](0011-own-streamable-http-edge.md), [ADR-0027](0027-mcp-edge-method-handlers.md), [ADR-0029](0029-dialects-and-dual-era-edge.md)

## Context

ADR-0011 established an internal Streamable-HTTP edge on FastAPI, and ADR-0029
introduced a dual-era edge (`Modern` vs. `Handshake`). However, implementation
in `mcp_edge.py` grew into a monolithic coordinator mixing HTTP admission,
database querying, era detection, session lifecycle, and SSE streaming.

Four structural issues emerged:
1. **Temporal Naming:** The name `Modern` is contextual and non-descriptive;
   future MCP revisions render "Modern" obsolete.
2. **Vague Nomenclature:** The name `McpEdge` is generic networking jargon
   rather than describing its role as a protocol router.
3. **DoS Vulnerability:** The edge previously acquired database connections
   and executed queries across five tables in `_admit()` before verifying that
   the incoming payload was valid JSON.
4. **Conditional Leakage:** Handshake session management (Valkey session
   loading, TTL touching, client reply signaling) was intertwined with
   stateless request handling.

## Decision drivers

- **Intrinsic naming** — replace contextual labels (`Modern` vs `Handshake`) with
  inherent architectural mechanisms (`Stateless` vs `Session`).
- **DoS defense by design** — sequence checks by strictly increasing resource cost:
  cheap in-memory gates first, external storage and database I/O last.
- **Single Responsibility Principle** — separate admission gating, protocol era
  adaptation, and SSE streaming into focused classes.
- **Honest transport modeling** — stateless MCP is strictly `POST`-only, while
  session MCP supports `POST`, `GET` (SSE), and `DELETE`.

## Decision

1. **Rename Eras:**
   - `Era.MODERN` ➔ `ProtocolEra.STATELESS` (self-describing per-request `_meta`,
     no server session).
   - `Era.HANDSHAKE` ➔ `ProtocolEra.SESSION` (stateful `initialize` handshake,
     `Mcp-Session-Id`, Valkey session).
2. **Rename Entrypoint:**
   - `McpEdge` ➔ `McpGatewayRouter`.
3. **Implement 3-Stage Admission Pipeline:**
   - Stage 1: Size limits (`Content-Length` < 4MB) & `Content-Type: application/json`.
   - Stage 2: In-memory `JsonRpcMessage` envelope validation (CPU only; immediate
     400 on malformed syntax).
   - Stage 3: Database / Cache admission (`BundleView` resolution and caller
     authentication).
4. **Adopt Front Controller + Protocol Adapters:**
   - `McpGatewayRouter` acts as the Front Controller, running the admission
     pipeline, identifying the era, and delegating to:
     - `StatelessMcpAdapter` (implements `handle_post()`).
     - `SessionMcpAdapter` (implements `handle_post()`, `open_stream()`, and
       `close_session()`).
5. **Extract SSE Streaming:**
   - Move SSE generation and keepalive loops into `SessionStream`, decoupling
     streaming transport details from JSON-RPC routing.
6. **Split the `api/mcp/` package by concern:**
   - `api/mcp/routing/` — the front door: front controller, admission gate, era
     adapters, session stream, and `authentication/` (whose only consumer is the
     admission gate).
   - `api/mcp/protocol/` — the wire vocabulary: the version-neutral JSON-RPC
     envelope, contexts, error helper, version/log/server-info, cache hints,
     forwarded headers, SSE framing, session header, and `dialect/` (the
     per-revision half of the same subject).
   - `api/mcp/dispatch/` — the method surface: `MethodRegistry`, the
     `MethodHandler` contract, the rate-limiting decorator/gate, and `handlers/`
     (one class per JSON-RPC method).
   - `api/mcp/relay/` — the bidirectional server-to-client machinery: the
     open-stream `ClientRelay` and the stateless `input_required` retry path.
   - `api/mcp/tool_call/` — the one method feature complex enough to own a
     package: the `tools/call` execution pipeline.
   - `api/mcp/controllers/` stays the FastAPI surface, per the project's
     controllers convention.

## Alternatives considered

- **Keep monolithic `McpEdge`:** Rejected because mixing transport, session
  management, and era branching creates high coupling and makes adding future
  revisions error-prone.
- **Pure Strategy Pattern across all HTTP verbs:** Rejected because stateless
  MCP does not support `GET` (SSE) or `DELETE`. Forcing dummy implementations
  violates the Interface Segregation Principle. Protocol Adapters honestly model
  differing transport capabilities.

## Consequences

### Positive

- Malformed or oversized requests fail in microseconds in memory without
  occupying database connections or starving connection pools.
- "Stateless" and "Session" accurately describe the architectural mechanism and
  will not rot with future MCP revisions.
- Each protocol adapter is tested in isolation; `StatelessMcpAdapter` contains
  zero Valkey session mocks.
- Modern/stateless clients attempting `GET` or `DELETE` are rejected cleanly
  with `405 Method Not Allowed`.

### Trade-offs

- Requires updating imports and test assertions referencing `McpEdge` or
  `Era.MODERN` across the test suite.
