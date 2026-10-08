# ADR-0011: Own the Streamable-HTTP endpoint edge; use FastMCP for the upstream side only

**Status:** accepted · **Date:** 2026-07-02 · **Amended by:** [ADR-0027](0027-mcp-edge-method-handlers.md),
[ADR-0029](0029-dialects-and-dual-era-edge.md),
[ADR-0035](0035-front-controller-protocol-adapters-and-admission-pipeline.md) (the edge is now a front controller over
two protocol adapters)

## Context

Specs 30/32 left an explicit open question ("the spike"): how much of FastMCP v3's session/transport layer can serve the
public endpoints given the requirement that session state must be externalized (SES-1/2)? Implementation established
that FastMCP's server-side Streamable-HTTP session manager binds a session to in-process objects — exactly the metamcp
failure mode ([ADR-0004](0004-postgres-redis-state-split.md) exists to eliminate it.)

## Decision drivers

- Any-replica serving (SES-2) is non-negotiable; adapting FastMCP's session manager would mean fighting, not using, the
  framework.
- The tools-first message surface is small; owning it costs little and makes the spec-32 delivery work (SSE streams +
  pub/sub routing) a natural extension of code we control.
- FastMCP's client side is excellent for upstreams: transports, handlers for progress/sampling/elicitation (needed by
  PROT-1/4), in-process testing.

## Decision

The public `/{endpoint}/mcp` edge is implemented **directly on FastAPI** (`gateway/mcp_endpoint.py`): JSON-RPC dispatch
for initialize/tools/list/tools/call/ping/notifications, with the session as a versioned Redis record
(`store/sessions.py`) loaded per request. **FastMCP v3 is used only on the upstream side** (`gateway/upstream.py` client
factory) and as in-process test servers.

## Alternatives considered

_Not recorded at the time of the decision._

## Consequences

### Positive

- Sessions survive restarts and hop replicas — proven by tests using two HTTP clients against one session.
- Hermetic end-to-end tests: FastAPI ASGI transport + in-process FastMCP upstreams + fakeredis.

### Trade-offs

- We own protocol-compliance for the messages we serve; the GET event stream (EP-1a) and progress/cancellation relay
  (PROT-1..3) are still to be built on this edge.
- New MCP protocol revisions must be tracked manually on the server edge (since 2026-09 the version and method tables
  are read from the SDK's `mcp_types` registry, so only revision-specific *shape* is hand-written; see
  [ADR-0029](0029-dialects-and-dual-era-edge.md)) (the client edge rides FastMCP releases).

