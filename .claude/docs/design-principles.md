# Design Principles & Engineering Guidelines

Core principles for architecture, naming, pattern selection, and resource protection in bundlemcp.

## 1. Intrinsic, Descriptive Naming Over Temporal Labels

Never name components, enums, or modules after temporal, relative, or subjective states (e.g. `modern`, `legacy`, `new`,
`v2`, `next`, `improved`).

### Why temporal names fail
Software outlives the moment it was authored. As soon as a newer specification or iteration lands, "modern" becomes the
legacy code, creating confusion and forcing breaking renames.

### The Rule
Name components after their **inherent architectural mechanism**, **protocol capability**, or **domain invariant**:
- ❌ `Era.MODERN` vs. `Era.HANDSHAKE` ➔ ✅ `ProtocolEra.STATELESS` vs. `ProtocolEra.SESSION`
- ❌ `NewAuthService` ➔ ✅ `OidcSessionService`
- ❌ `ImprovedCallHandler` ➔ ✅ `StreamedCallHandler`

### In this repo
`ProtocolEra` (`api/mcp/protocol/dialect/era.py`) is the worked example, and
ADR-0035 made the rename. Two things about its current state are deliberate, and
knowing which is which saves you a pointless refactor:

- **`modern_versions`, `has_modern_meta`, `MODERN_PROTOCOL_VERSIONS`** mirror the
  MCP SDK's own vocabulary. Matching an external API's names beats internal
  purity; renaming them would make the gateway harder to read against the SDK.
- **`BUNDLEMCP_LEGACY_PROTOCOL_ENABLED`** is a genuine violation, and the one
  outstanding item. It is operator-facing configuration, so renaming it breaks
  deployments; it changes with a deprecation, not in passing.

The `ModernDialect` / `HandshakeDialect` class names sit in the first category —
they name the revision family the SDK names that way.

## 2. Concrete Domain Roles Over Vague Jargon

Avoid ambiguous networking or framework buzzwords like `Edge`, `Core`, `Base`, `Handler` (when generic), or `Service`
(when untyped).

A developer inspecting a directory tree should instantly grasp each module's responsibility:
- ❌ `mcp_edge.py` (vague CDN/networking term) ➔ ✅ `gateway_router.py` (it routes protocol messages)
- ❌ `helpers.py` / `utils.py` ➔ ✅ Concrete domain module (see `module-naming.md`)

## 3. Asymmetric Resource Protection (DoS Defense by Design)

Request handling pipelines must always sequence validation in order of **strictly increasing resource cost**:

```
1. Transport & Size Gate        (Nanoseconds, 0 allocations)
       ▼
2. Syntactic & Envelope Parse   (Microseconds, pure CPU)
       ▼
3. Storage & Database Admission (Milliseconds, locks DB pool connections)
```

### The Rule
- **Never open a database connection or Unit of Work** before verifying that the incoming payload respects the body size
  limit and is well-formed JSON.
- Exhausting database connection pools with malformed or unvalidated garbage payloads is a severe availability hazard.

### In this repo
`RequestBodyLimit` (`api/http/request_body_limit.py`) is stage 1, ahead of
routing; `McpGatewayRouter.post` (`api/mcp/routing/gateway_router.py`) runs the
rest, and `AdmissionGate` is stages 2 and 3:

| Stage | Where | Cost |
|---|---|---|
| `RequestBodyLimit` — declared `Content-Length` over `max_request_bytes` (4 MiB) → `413`; a chunked body counted as it streams | `request_body_limit.py` | One header read; a byte count per chunk |
| `parse_envelope` — `await request.json()` into `JsonRpcMessage` | `admission_gate.py` | Pure CPU |
| `admit_caller` — endpoint lookup and authentication in one `UnitOfWork` | `admission_gate.py` | A pooled DB connection |

This ordering is what ADR-0035 bought: before it, `_admit()` queried five tables
*before* checking that the body was valid JSON. One honest caveat about the
current implementation, so nobody documents it as done:

- **There is no `Content-Type` check.** The size limit and the JSON parse are the
  whole of stages 1 and 2.

The limit is read from the runtime-config snapshot (`RuntimeConfig.snapshot`), never
from Postgres, so stage 1 stays free of I/O even though operators can change it.

## 4. Honest Pattern Modeling Over Flat Conditionals

Avoid scattering `if / elif / else` branches across monolithic coordinators. Model differing capabilities honestly using
design patterns:

1. **Front Controller + Protocol Adapters:** Use when different protocol versions share an endpoint URL but exhibit
   fundamentally different transport capabilities (e.g., stateless MCP is POST-only; session MCP supports POST, GET-SSE,
   and DELETE).
2. **Pipes & Filters (Pipelines):** Use for multi-step operational chains that require cross-cutting concerns (Auth ➔
   Pre-metering ➔ Execution ➔ Settlement ➔ Audit).
3. **State Machines:** Use when operations depend strictly on protocol lifecycle stages (e.g., Handshake session
   transitions: `Uninitialized` ➔ `Active` ➔ `Closed`).

### In this repo

| Pattern | Implementation |
|---|---|
| Front Controller + Protocol Adapters | `McpGatewayRouter` over `StatelessMcpAdapter` / `SessionMcpAdapter` (`api/mcp/routing/`), ADR-0035 |
| Registry instead of a dispatch conditional | `MethodRegistry` (`api/mcp/dispatch/`), ADR-0027 — see [controllers.md](controllers.md) |
| Pipes & Filters | `ToolCall` (`api/mcp/tool_call/tool_call.py`): credentials ➔ metering ➔ upstream ➔ settlement ➔ audit, with `RateLimited` as a decorator filter at registration |

The shape to avoid is the one all three replaced: a single coordinator branching
on protocol version, method name and auth mode in the same function body.
