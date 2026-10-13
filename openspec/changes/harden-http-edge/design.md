# Design: harden the HTTP edge

## Context

See `proposal.md` for the gaps. The current shape of each control:

- **Egress.** `infrastructure/egress/egress_policy.py::check_url_allowed` resolves the hostname with `getaddrinfo` and
  judges every address. Callers run it before building a client: `infrastructure/fastmcp/client_factory.py` (every
  upstream MCP connection), `infrastructure/oidc/jose_oidc_provider.py`, `infrastructure/httpx/
  upstream_oauth_provider.py` and `client_metadata_fetcher.py`. The HTTP client then resolves again. The MCP SDK's
  Streamable HTTP transport (on `httpx2`) follows redirects that stay within the endpoint's origin
  (`stream_within_origin`); the gateway's own `httpx` clients do not follow redirects. `StreamableHttpTransport`
  accepts an `httpx_client_factory`, which is the seam for the MCP side.
- **Size.** `McpGatewayRouter._is_oversized` compares a declared `Content-Length` against a module constant
  (`MAX_PAYLOAD_BYTES`, 4 MiB) and returns a plain-text 413; nothing bounds a chunked body, `/api/v1`, or an upstream
  response.
- **CORS.** `main/app.py` adds one `CORSMiddleware` with the `BUNDLEMCP_WEB_ORIGINS` allow-list and credentials, for
  every route, and only when web origins are configured.
- **Proxy headers.** `api/http/client_ip.py` takes the leftmost XFF entry from a trusted peer. Separately, uvicorn's own
  `proxy_headers` handling is on by default and trusts `127.0.0.1` (`FORWARDED_ALLOW_IPS`), so on a host-run gateway
  behind a local proxy uvicorn rewrites the socket peer before the gateway's policy runs.

## Goals / Non-Goals

**Goals:**

- One enforcement point for egress that sees the dialled address, shared by the MCP client and the gateway's own HTTP
  clients.
- Size limits enforced before parsing and before the admission stage takes a database connection
  ([design-principles §3](../../../.claude/docs/design-principles.md)), for chunked bodies too.
- One interpreter of forwarding headers.

**Non-Goals:**

- CORS for the OAuth metadata, registration and token endpoints. A browser-based client needs them too, but the
  requirement here is the MCP route; a separate change can extend SEC-5 when a browser client asks for it.
- An HTTP proxy for egress (`HTTP_PROXY`): the gateway's clients stop reading proxy variables from the environment
  (below); supporting an egress proxy is a separate decision.
- Response caps for the gateway's own small fetches (OIDC discovery, metadata documents); they already read bounded
  JSON documents and are out of the SEC-7 scope.

## Decisions

### 1. Egress is enforced in the connection layer, not before it

A guarded network backend (infrastructure, `infrastructure/egress/`) replaces the pre-flight check: when the
connection pool asks it to open a TCP connection to `(host, port)`, it resolves the host once, judges every address
with the existing policy, and dials a vetted address itself. TLS is then started with the original hostname for SNI
and certificate verification, which the pool passes separately, so HTTPS keeps working unchanged. Because every
connection — including the one a followed redirect opens — goes through the backend, redirect coverage needs no
redirect-specific code. The policy function keeps its rules and gains the new blocks; it becomes a pure judgement
over an address (domain-free, still in `infrastructure/egress/`, since it reads `Settings`).

Both client stacks get the backend: an `httpx_client_factory` handed to `StreamableHttpTransport` for the MCP side
(`httpx2`), and a shared client builder for the `httpx` clients in `infrastructure/httpx/` and `infrastructure/oidc/`.
Every builder sets `trust_env=False`, so an `HTTP_PROXY` in the environment cannot route around the check by making
the dialled address the proxy's. `check_url_allowed` stays only as an early, cheap refusal with a clear error
(SEC-3's `egress_denied` state for probes and inspection); it is no longer the enforcement.

*Alternatives:* resolve once and rewrite the URL's host to the vetted IP with a `Host` header and an SNI extension —
works for `httpx`, but every redirect and every client needs the rewrite, and the MCP SDK builds its own requests;
a proxy-style forward guard (smokescreen-like sidecar) — strongest isolation, but a new deployable for a self-hosted
gateway; keeping the pre-flight and disabling redirects — leaves the rebinding window open.

### 2. IPv4-mapped and unspecified addresses are normalised in the policy

Before judging, an `IPv6Address` with `ipv4_mapped` set is replaced by that IPv4 address, so `::ffff:169.254.169.254`
meets the `169.254.0.0/16` block and an operator's IPv4 allow/deny entries. `0.0.0.0/8` and `::/128` join the
loopback blocks because Linux connects them to the local host; `fd00:ec2::254/128` is a single-address block inside
otherwise-allowed ULA space.

### 3. Size limits are a body-limit ASGI middleware plus a header gate

An ASGI middleware (api layer, `api/http/`) wraps `receive` for requests under `/api/v1` and `/{endpoint}/mcp`,
counting bytes and raising a dedicated exception once the limit is crossed; a declared `Content-Length` above the limit
is refused before the first `receive`. The router's `_is_oversized` gate goes away in favour of the middleware, which
runs earlier still. The rejection is rendered per surface: a JSON-RPC error (`id: null`, code `-32600`, message naming
the limit) for MCP routes, the API's `{"detail": …}` object for `/api/v1`.

The limit is read from a runtime-config **snapshot** the middleware holds in memory, never from Postgres: the
`RuntimeConfig` cache gains a non-loading accessor that returns the last loaded value (or the registry default before
the first load), and an invalidation event reloads it in the background. This keeps stage 1 of the admission pipeline
free of I/O. A replica therefore applies a changed limit after the invalidation event reaches it, which the spec allows.

*Alternatives:* Starlette's per-route body reading with a check in each handler — misses `/api/v1` handlers that let
FastAPI parse the body; an environment setting instead of runtime config — the original asks for runtime-configurable,
and the snapshot makes it free.

### 4. The upstream response cap counts bytes per message in the transport

The `httpx2` client the MCP transport receives (decision 1) wraps response streams in a byte counter that resets at
each SSE event boundary and for each JSON response body; crossing the cap closes the stream and raises a typed error
that the tool-call pipeline (`api/mcp/tool_call/`) maps to a structured MCP error. A per-stream cap was rejected: a
session's long-lived SSE stream legitimately carries far more than 16 MiB over its life.

### 5. CORS is chosen by path

`main/app.py` replaces the global `CORSMiddleware` with two instances behind a small path dispatcher (api layer): the
MCP-route policy (reflect any origin, no credentials, methods `GET, POST, DELETE, OPTIONS`, request headers
`Authorization, Content-Type, Accept, Mcp-Session-Id, MCP-Protocol-Version, Last-Event-ID, X-API-Key`, expose
`Mcp-Session-Id, WWW-Authenticate`) for `/{endpoint}/mcp`, and the SEC-4 allow-list for everything else. Reflecting
any origin is safe because these routes accept no ambient credential: the admission gate never reads the admin session
cookie, and SEC-5 now states that as a requirement so a later change cannot add it.

### 6. One interpreter of forwarding headers

`apps/gateway/main.py` passes `proxy_headers=False` to uvicorn, so the gateway's own policy is the only place forwarding
headers are read. `api/http/client_ip.py` walks `X-Forwarded-For` right to left, skipping trusted-proxy entries, and a
small ASGI middleware (api layer) applies `X-Forwarded-Proto`/`X-Forwarded-Host` from a trusted peer to the request
scope. Feeding `BUNDLEMCP_TRUSTED_PROXIES` into uvicorn's `forwarded_allow_ips` was rejected: two interpreters drift,
and uvicorn's rules for the client entry are not the ones DEP-2 specifies.

### 7. AUTH-29 strip is case-insensitive

`HeaderForwarding.headers_for` removes every key equal to `X-MCP-User` ignoring case before injecting its own header.
No spec change: AUTH-29 already requires the strip to be unconditional.

### 8. An ADR records the enforcement point

A new ADR, "Egress policy enforced at connect time", extends ADR-0032 (which fixed the policy's scope) with where it is
enforced and why `trust_env` is off.

## Risks / Trade-offs

- [The `httpx2` connection layer may not expose a network-backend seam like `httpcore`'s] → Spike first (task 1.1);
  fall back to the URL-rewrite alternative for the MCP side only, keeping the backend for the `httpx` clients.
- [Connect-time denial surfaces later than a pre-flight, mid-request] → The early `check_url_allowed` stays for a clear
  error; the connect-time denial raises the same `EgressDenied` type so callers' handling is unchanged.
- [Lowering the default body limit to 1 MiB breaks clients posting large arguments] → Recorded as an open decision;
  the limit is runtime-configurable, and the release notes call it out.
- [Rightmost-untrusted needs proxies that append to XFF] → nginx's `$proxy_add_x_forwarded_for` and Traefik/Caddy
  defaults do; `deploy.md` says so, and a proxy that overwrites XFF still yields the right answer.
- [Reflecting every origin on MCP routes] → Safe only without ambient credentials; covered by the SEC-5 cookie clause
  and a test that a session cookie never authenticates on an MCP route.

## Migration Plan

No data migration. Operators with a proxy body limit below the new request limit need nothing; those relying on bodies
between 1 and 4 MiB raise the runtime limit before upgrading. Rollback is a redeploy of the previous image; the two new
runtime-config keys are ignored by older versions.
