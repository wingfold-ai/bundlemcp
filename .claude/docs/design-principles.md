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
- **Never open a database connection or Unit of Work** before verifying that the incoming payload is well-formed JSON,
  has the correct `Content-Type`, and respects body size limits (`Content-Length` < 4MB).
- Exhausting database connection pools with malformed or unvalidated garbage payloads is a severe availability hazard.

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
