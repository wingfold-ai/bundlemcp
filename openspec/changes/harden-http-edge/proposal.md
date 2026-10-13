# Proposal: harden the HTTP edge

## Why

Four controls at the gateway's HTTP boundary are weaker than the original security specification asked for, and two
of them are exploitable today:

- **Client-IP spoofing behind a proxy.** With trusted proxies configured, the gateway takes the **leftmost**
  `X-Forwarded-For` entry, which the client writes itself. A client can choose the IP its rate limit, auth-failure
  lockout and registration limit are counted against, and so escape all three.
- **DNS rebinding.** The egress policy resolves an upstream's hostname as a pre-flight check, then the HTTP client
  resolves it again to connect. A name whose answer changes in between reaches a blocked address (cloud metadata,
  loopback). The policy also misses IPv6 metadata (`fd00:ec2::254`), IPv4-mapped IPv6 forms of blocked addresses, and
  the unspecified addresses that Linux routes to loopback. `docs/self-hosting/deploy.md` says redirects are not
  followed, but the MCP client follows same-origin redirects.
- **Size limits.** Only a declared `Content-Length` on `/{endpoint}/mcp` is checked (fixed 4 MiB); a chunked body is
  read unbounded, `/api/v1` has no limit, and an upstream response has no cap, so one tool result can exhaust a
  replica's memory.
- **CORS on MCP endpoints.** One global allow-list policy with credentials applies everywhere, so browser-based MCP
  clients on any other origin cannot read `/{endpoint}/mcp` responses or its `WWW-Authenticate` challenge.

A related bug in implemented behaviour: the identity header is stripped case-sensitively, so a mapping whose upstream
side is spelled `x-mcp-user` forwards a client-supplied value under the gateway's identity header (AUTH-29).

## What Changes

- **Egress at connect time (SEC-2).** The policy is judged on the address each connection actually dials, at connect
  time, for every connection the gateway opens to an admin- or remote-supplied URL — including each redirect hop. The
  built-in blocks add `fd00:ec2::254/128`, `0.0.0.0/8` and `::/128`, and an IPv4-mapped IPv6 address is judged as the
  IPv4 address it maps.
- **Permissive CORS on MCP endpoints (SEC-5, new).** `/{endpoint}/mcp` reflects the request's `Origin`, never allows
  credentials, and exposes `Mcp-Session-Id` and `WWW-Authenticate`. `/api/v1` keeps the SEC-4 allow-list.
- **Body and response limits (SEC-7, EP-9).** A request-body limit (default 1 MiB, runtime-configurable) on
  `/{endpoint}/mcp` and `/api/v1`, enforced while the body streams in, so chunked bodies are bounded too; an upstream
  response cap per message (default 16 MiB, runtime-configurable). Over-limit requests get 413 with a structured body
  (a JSON-RPC error on MCP routes); an over-limit upstream response becomes a structured MCP error to the caller.
  **BREAKING:** the default request limit drops from 4 MiB to 1 MiB.
- **Proxy headers (DEP-2).** From a trusted peer the client IP is the **rightmost** `X-Forwarded-For` entry that is not
  itself a trusted proxy; `X-Forwarded-Proto` and `X-Forwarded-Host` are honoured from trusted peers for the request's
  own scheme and host, while every published URL still comes from the public URL (DEP-1).
- **AUTH-29 fix (task, no delta).** The client-supplied identity header is stripped case-insensitively, so no mapping
  can forward it.

## Open decision

- **DEP-2: `X-Forwarded-Proto`/`X-Forwarded-Host`.** DEP-1 already derives every externally visible URL and the
  cookie's `Secure` flag from `BUNDLEMCP_PUBLIC_URL`, never from request headers, so honouring these two headers
  changes only the scheme and host the application sees on the request (logs, redirects that are relative today). The
  delta builds it as the original asked. The alternative is to **amend** DEP-2 to say the gateway deliberately ignores
  both because DEP-1 makes them unnecessary; then drop task 4.3. Either way the client-IP fix stands.
- **SEC-7: the 1 MiB default.** The original specification set 1 MiB; the gateway has shipped 4 MiB, and operators'
  proxy configs (`docs/self-hosting/deploy.md`) are written for it. Lowering the default is breaking for any client
  that posts large tool arguments. The delta keeps 1 MiB as specified; the maintainers may instead keep 4 MiB as the
  default (only the number in SEC-7, EP-9 and the docs changes).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `security`: SEC-2 (connect-time enforcement, redirects, IPv6 metadata, IPv4-mapped and unspecified addresses), SEC-5
  (added: CORS on MCP endpoints), SEC-7 (configurable limits on both surfaces, chunked bodies, upstream response cap).
- `endpoints`: EP-9 (the MCP route's view of the SEC-7 limit).
- `deployment`: DEP-2 (rightmost untrusted `X-Forwarded-For`; `X-Forwarded-Proto`/`Host` from trusted peers).

## Impact

- **Code:** `infrastructure/egress/` (policy and a connect-time guarded transport), `infrastructure/fastmcp/
  client_factory.py` and every `infrastructure/httpx/` and `infrastructure/oidc/` client builder, `main/app.py`
  (path-scoped CORS, body-limit middleware), `api/mcp/routing/gateway_router.py` (the size gate),
  `api/http/client_ip.py`, `apps/gateway/main.py` (uvicorn's own proxy-header handling),
  `domain/config/config_registry.py` (two keys), `api/mcp/protocol/header_forwarding.py` (AUTH-29 fix).
- **APIs:** CORS headers on `/{endpoint}/mcp`; 413 bodies become structured; `/api/v1` gains a 413. No DTO changes
  except the runtime config listing, which gains two keys.
- **Operators:** reverse-proxy body limits must be at least the configured limit; proxies listed in
  `BUNDLEMCP_TRUSTED_PROXIES` must append to `X-Forwarded-For` (the nginx default). Documented in
  `docs/self-hosting/deploy.md`, `configuration.md`, `troubleshooting.md`, `docs/integrate/http-surface.md`.
- **ADR:** a new ADR, "Egress policy enforced at connect time", extending ADR-0032 (scope) with the enforcement point.
- **Dependencies:** `fix-stale-documentation` makes the redirect sentence in `deploy.md` honest in the meantime; this
  change replaces it with the real behaviour. `improve-request-observability` also modifies DEP-2 (its logging clause);
  whichever change is archived second rebases its DEP-2 block on the other. `add-prometheus-metrics` may count 413s
  and egress denials; not required here.
