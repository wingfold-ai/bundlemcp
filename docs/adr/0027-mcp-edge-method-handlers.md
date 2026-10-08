# ADR-0027: The MCP edge dispatches through a method registry; a tool call is an object

**Status:** accepted · **Date:** 2026-09-03 · **Amended by:** [ADR-0029](0029-dialects-and-dual-era-edge.md),
[ADR-0035](0035-front-controller-protocol-adapters-and-admission-pipeline.md) (dispatch moved from the edge class into
the protocol adapters) · **Amends:** [ADR-0011](0011-own-streamable-http-edge.md), [ADR-0016](0016-relay-design.md),
[ADR-0026](0026-controllers.md)

## Context

The MCP edge's POST handler compared the JSON-RPC method against fourteen string literals and called a free function for
each, passing the same six positional arguments (`runtime, request, view, record, body, rpc_id`) into every one, most of
them unannotated. The rate-limit gate was copied into three branches. The tools/call path was a 290-line module whose
streaming helper took eleven positional parameters, carried its per-call state in a mutable dict and two one-element
lists, and rendered the JSON-RPC result twice. Upstream credential resolution was written once for tool calls and once
for the read-only passthrough. Server-to-client relay handlers were a dict of closures keyed by string, and
authentication was an if-chain over the endpoint's modes returning a tuple.

Adding a method meant editing the dispatcher; testing a handler meant building the whole app.

## Decision drivers

- A registry turns "add a method" into "register a handler". The dispatcher never changes again.
- Handlers with explicit dependencies are unit-testable with fakes.
- The credential logic and the JSON-RPC rendering were each written twice; both now exist once.
- A strategy per credential kind is the shape the endpoint's `auth_modes` already has.

## Decision

- **`McpEdge` is the edge as an object.** It admits a request (endpoint lookup, authentication, session load) and hands
  a typed `SessionContext` plus a parsed `JsonRpcMessage` to `MethodRegistry.dispatch`. The registry maps method names
  to `MethodHandler` instances: an unregistered notification is acknowledged, an unregistered request gets
  method-not-found. Handlers declare their own constructor dependencies. `RateLimited` is a decorator handler, so the
  gate exists once. `McpEndpointController` is the HTTP surface; `McpEdgeAssembly` is the typed input the composition
  root hands to `build()`, replacing the runtime bag every function used to receive.
- **Authentication is a strategy list.** `EndpointAuthentication` tries `OAuthBearerAuthenticator`,
  `ApiKeyAuthenticator` and `AnonymousAuthenticator` in precedence order, filtered by the endpoint's modes.
  `AuthFailureGuard` counts failures per client IP for every credential edge, beside the limiter it drives.
- **tools/call is a pipeline object.** `ToolCall` carries the call's state through credential resolution, metering, the
  upstream call and accounting; `BufferedCallResponse` and `StreamedCallResponse` differ only in how bytes leave.
  `UpstreamCall` owns timeout and cancellation as attributes rather than closure cells. `ClientRelay` offers the
  client-side capabilities to the upstream, gated by what the client advertised. `UpstreamCredentialResolver` is the one
  place the upstream Authorization header is decided. `AuditContext` replaces the mutable kwargs dict; `CallOutcome`
  renders itself as JSON-RPC.
- **The read-only passthrough shares `MemberFanout`**, which reaches members with the same headers and credentials the
  tool path uses.

## Alternatives considered

_Not recorded at the time of the decision._

## Consequences

### Positive

- Zero `if method ==` branches remain in the edge.
- The composition root builds the edge from one typed assembly; the `GatewayRuntime` bag and its `app.state.gateway`
  reads are gone.

### Trade-offs

- A handler class per method is more files than one dispatcher. The files are small and named for the method they serve.
- The upstream client library recognises handlers with `inspect.isfunction`, so the relay offers its bound methods
  through thin function wrappers.

