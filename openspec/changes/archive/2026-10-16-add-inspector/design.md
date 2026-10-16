# Design

## Context

See proposal.md for motivation. What exists:

- `UpstreamClientFactory` (contract in `application/contracts/upstream/`, FastMCP adapter in
  `infrastructure/fastmcp/client_factory.py`) builds a FastMCP `Client` for an `McpServer`, applying the egress check
  (SEC-1) and the stored static headers. Upstream OAuth tokens are added by the callers through `extra_headers`.
- `ServerInspectionService` already probes a transient, never-stored `McpServer` for UPS-11; the same pattern serves
  ad-hoc targets.
- The MCP edge serves `/{endpoint}/mcp` through `McpGatewayRouter`, with admission, authentication, profile, curation,
  metering and audit.
- CLAUDE.md: no in-memory-only state a request depends on; any replica serves any request.

## Goals / Non-Goals

**Goals:**

- One proxy for all three target kinds, so the UI has one protocol to speak.
- Endpoint targets behave exactly as a real client sees them, including audit (UI-11).
- Restart-safe and replica-agnostic: no inspector session held in a process.

**Non-Goals:**

- Resources, prompts, roots, sampling, saved collections (proposal, out of scope).
- Serving server-initiated requests (elicitation, sampling) during an inspector call: the inspector advertises no such
  client capabilities, so a tool that needs them fails visibly.

## Decisions

### D1. Stateless proxy: every operation is connect → initialize → operation → close

Each inspector request names its target and opens a fresh client for the operation, so any replica serves it and a
restart loses nothing. The cost is an `initialize` per operation; the response reports both the initialize time and
the operation time, so the timing shown for a call is not inflated by it.

*Alternative:* a long-lived inspector session per browser tab, held in process or rebuilt from Valkey. Rejected: it
breaks the replica rule (or needs the session-pooling machinery of `add-upstream-session-pooling`) for a debugging
tool where a few extra milliseconds do not matter.

### D2. Three target adapters behind one use case

`InspectorService` (`application/inspection/`) takes an `InspectorTarget` (a discriminated union: `upstream` by name,
`endpoint` by name with an optional credential, `adhoc` with URL and headers) and resolves it to a client:

- **upstream** — the stored `McpServer` through `UpstreamClientFactory`, with the upstream OAuth token the shared
  identity uses, or for a per-user upstream the admin's own token (a service key cannot inspect a per-user upstream:
  `409` naming the reason).
- **adhoc** — a transient `McpServer` (never stored) through the same factory, so the egress policy applies unchanged
  (UI-10, SEC-1).
- **endpoint** — a new contract `GatewayEndpointClientFactory` (`application/contracts/upstream/`), fulfilled in
  `infrastructure/fastmcp/` by a FastMCP client whose HTTP transport is an in-process ASGI transport onto the
  gateway's own app, wired in `main/`. The request enters `/{endpoint}/mcp` like any client's, so authentication,
  profile, curation, metering, rate limits and audit apply (UI-8b, UI-11), without leaving the process — so the
  gateway's own loopback address never meets the egress policy, and the public hostname need not resolve from inside
  the container.

The endpoint target needs a credential the endpoint accepts: an API key scoped to it, or a bearer token for an OAuth
endpoint, entered by the admin and used for that request only; `none`-auth endpoints need none.

### D3. Routes and streaming

`InspectorController` (`api/management/controllers/`, a `ManagementController`) under `/inspector`:
`POST /inspector:connect` (initialize, returns server info, protocol revision and capabilities), `POST
/inspector:ping`, `POST /inspector:list-tools`, and `POST /inspector:call-tool`, which answers `text/event-stream`:
progress notifications as they arrive, then one result or error event with timings. The browser reads it with
`fetch` streaming (it is a `POST` with a body, so `EventSource` does not apply). Request and response DTOs live in
`application/schemas/inspector/`.

*Alternative:* one generic JSON-RPC passthrough route. Rejected: it would let the browser send any method to a target
with stored credentials, which is wider than the four operations UI-9 needs and harder to audit.

### D4. Attribution

For upstream and ad-hoc targets the service binds `source="inspector"` and the admin's principal to the structlog
context for the duration of the operation, and writes no audit record (UI-11). Endpoint targets carry no extra marker
in the audit record: they are audited exactly as a client, per UI-11.

### D5. UI

The page lists targets (upstreams and endpoints from the existing list routes, plus an ad-hoc form), shows the
capability view, the tool list with schemas, and a call form generated from the JSON Schema with a raw-JSON toggle.
Form generation is client-side from the tool's `inputSchema`; unsupported schema constructs fall back to raw JSON.

## Risks / Trade-offs

- [An admin calls a destructive tool by accident] → the call button shows the tool's annotations
  (`destructiveHint`) and asks for confirmation when set.
- [Inspector traffic to endpoints is metered and billed through the metering hook] → intended (real public path);
  documented, so operators use a test key or a test endpoint.
- [Ad-hoc headers carry secrets] → they are used for one request and never logged or stored (SEC-10); tests assert it.
- [Per-operation initialize is slow for some upstreams] → acceptable for a debugging tool; timing shows it separately.

## Migration Plan

Additive. Rollback removes the routes and restores the placeholder page.

## Open Questions

- Whether the inspector should later mint a short-lived credential for an OAuth endpoint on the admin's behalf instead
  of asking for a pasted token; the routes and specs stay the same either way.
