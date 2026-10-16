# ADR-0058: The inspector is proxied by the management API, and reaches endpoints in-process

**Status:** accepted · **Date:** 2026-10-16

## Context

Admins debug upstreams and endpoints by asking the same questions again and again: does the tool exist, what does its
schema say, what does a call return through this endpoint's profile. Until now that needed the reference MCP inspector
running beside the gateway, with credentials copied out of it, and the admin UI's Inspector page was a placeholder.

A browser cannot do this itself: stored upstream credentials must never reach it, most upstreams send no CORS headers,
and an internal upstream is not reachable from the admin's machine at all.

## Decision drivers

- Stored secrets stay on the gateway.
- An endpoint is inspected as its clients see it: authentication, profile, curation, metering and audit.
- No inspector state in a process: any replica serves any inspector request, and a restart loses nothing.
- Ad-hoc URLs are admin-supplied URLs, so the egress policy applies to them as to every other.

## Decision

- **Four management routes, not a passthrough.** `POST /api/v1/inspector:connect`, `:ping`, `:list-tools` and
  `:call-tool`, each naming its target: a registered upstream, an endpoint of this gateway, or an ad-hoc URL with
  headers. `:call-tool` answers with Server-Sent Events, progress first and the outcome last; the browser reads them
  with `fetch`, since the stream answers a `POST`.
- **Connect per operation.** Each request opens a connection, initialises, runs its one operation and closes. The
  response reports the initialisation time beside the operation's own, so the cost is visible rather than hidden.
- **Upstream and ad-hoc targets use the gateway's client factory**, the one tool calls use, so the egress policy, the
  response cap and the stored static headers apply unchanged. Upstream OAuth uses the shared account or, for a
  per-user upstream, the admin's own; a service key has no account and is refused. A credential value a target echoes
  back is redacted before anything reaches the browser. These calls are logged with `source=inspector` and audited
  nowhere.
- **Endpoint targets are dispatched in-process.** A `GatewayEndpointClientFactory` contract is fulfilled by an MCP
  client whose HTTP transport hands each request to the gateway's own ASGI app and streams the response back. The
  request enters `/{endpoint}/mcp` like any client's, with the credential the admin entered, and is audited and
  metered like any client's. Nothing is dialled, so neither the gateway's loopback address nor its public hostname has
  to be reachable from inside the container, and the egress policy is not involved.

## Alternatives considered

- **A generic JSON-RPC passthrough.** It would let the browser send any method to a target with stored credentials:
  wider than the four operations the page needs, and harder to reason about.
- **A long-lived inspector session per browser tab.** Fewer initialisations, but it either breaks the replica rule or
  needs the session-pooling machinery for a debugging tool where a few milliseconds do not matter.
- **Endpoint targets over the public URL.** The public hostname often does not resolve from inside the container, and
  the request would leave and re-enter through the proxy only to reach this same process.
- **httpx's own ASGI transport.** It collects the whole response before returning, which would hold progress
  notifications back until the call ends.

## Consequences

### Positive

- One protocol for the UI over three kinds of target, with no secret in the browser and no CORS to arrange.
- An endpoint shows exactly what its clients see, curation and profile included.

### Trade-offs

- Every operation pays an initialisation; a slow upstream feels slow. The timing shows it separately.
- Inspector calls through an endpoint are metered like any client's, so they may be billed; operators use a test key
  or a test endpoint.
- Ping is a handshake-era method: a target speaking the stateless revision answers it as unsupported, and the
  inspector shows that answer.
- The inspector advertises no client capabilities, so a tool that asks for elicitation or sampling fails visibly
  rather than prompting the admin.
