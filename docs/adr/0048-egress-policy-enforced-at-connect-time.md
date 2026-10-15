# ADR-0048: The egress policy is enforced at connect time

**Status:** accepted · **Date:** 2026-10-15 · **Extends:** [ADR-0032](0032-egress-policy-scope.md)

## Context

ADR-0032 decided which outbound requests pass the egress policy. Where it was enforced was a pre-flight:
`check_url_allowed` resolved the URL's host and judged every address, and then the HTTP client resolved the host again
to connect. A name whose answer changed between the two lookups (DNS rebinding) reached whatever the second answer
named, a cloud metadata service or the gateway's own loopback included. The MCP transport also follows redirects
within an upstream's origin, and a redirect's connection was never judged at all. The policy itself missed AWS's IPv6
metadata address, IPv4-mapped IPv6 forms of the blocked ranges, and the unspecified addresses that Linux routes to the
local host.

Two HTTP stacks open these connections: `httpx` (upstream OAuth, the client-metadata fetcher, the OIDC relying party)
and `httpx2` (the MCP client). A spike established that neither `httpx.AsyncHTTPTransport` nor
`httpx2.AsyncHTTPTransport` takes a network backend, but the connection pool underneath each (`httpcore` and
`httpcore2`, which share one backend interface) does, and that both pools start TLS with the request's host name
rather than the address the backend dialled.

## Decision drivers

- The address judged must be the address connected to, for every connection, a redirect hop included (SEC-2).
- One enforcement point for both HTTP stacks, with no per-client or per-redirect code.
- TLS must keep verifying the upstream's certificate against its host name.

## Decision

- **A guarded network backend dials the vetted address.** `GuardedNetworkBackend` (`infrastructure/egress/`) wraps a
  pool's own backend: asked to connect to a host, it resolves it once, judges every address, and dials a vetted address
  itself, so the HTTP library never resolves the name again. The pool still passes the host name for SNI and
  certificate verification.
- **Both stacks are guarded the same way.** `guarded_client` builds the `httpx` clients and `guarded_mcp_http_client`
  is the MCP transport's client factory; each wraps its transport's pool with `guard_pool`. That sets a private pool
  attribute, since no public seam exists; `guard_pool` fails closed if the attribute is missing, and tests assert every
  client's pool is guarded, so a library change breaks a test instead of disabling the policy.
- **`trust_env` is off** on these clients, so an `HTTP_PROXY` in the environment cannot make the dialled address the
  proxy's and route around the policy.
- **The MCP client never follows redirects itself.** FastMCP asks a custom client factory for `follow_redirects=True`;
  the factory ignores it, keeping the SDK's behaviour where only the transport follows a redirect, and only within the
  upstream's origin.
- **`check_url_allowed` stays as an early refusal** with a clear error (a probe's `egress_denied` state); it is no
  longer the enforcement. A denial raised at connect time arrives wrapped by the MCP client, and the probe looks for it
  in the exception chain so the state is the same.
- **The policy normalises before judging**: an IPv4-mapped IPv6 address is judged as its IPv4 address, and
  `fd00:ec2::254/128`, `0.0.0.0/8` and `::/128` join the built-in blocks.

## Alternatives considered

- **Resolve once and rewrite the URL's host to the vetted IP**, with a `Host` header and an SNI extension. Works for one
  `httpx` request, but every redirect and every client needs the rewrite, and the MCP SDK builds its own requests.
- **A forward proxy that enforces the policy** (a smokescreen-like sidecar). The strongest isolation, but a new
  deployable for a self-hosted gateway.
- **Keep the pre-flight and turn redirects off.** Leaves the rebinding window open, and breaks upstreams that redirect
  `http` to `https`.

## Consequences

### Positive

- DNS rebinding and redirects cannot reach a blocked address, on any connection the gateway opens to an admin- or
  remote-supplied URL.
- One class enforces the policy for both HTTP stacks.

### Trade-offs

- The guard dials an IP, so it tries a host's addresses one after another instead of racing them; a dual-stack upstream
  whose first address is unreachable waits for that connect to fail.
- It depends on a private attribute of `httpcore`/`httpcore2` connection pools, covered by tests rather than by an API.
- The metering hook's client is not guarded: its URL is operator configuration for the application layer, usually on
  the same host or network, which the policy's loopback block would refuse.
