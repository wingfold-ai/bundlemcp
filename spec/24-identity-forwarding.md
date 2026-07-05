# 24 — Identity & header forwarding

**Status:** Accepted · **Origin:** metamcp carry-over (fork feature `forward_headers` + application-layer's identity contract)
**Prior art:** `../metamcp/apps/backend/src/lib/metamcp/header-forwarding.ts`, `../application-layer/deploy/docker-compose.yml` (seo-gsc/hyperframes identity contract)

## Summary

Upstream servers often need to know **who** is calling (per-user storage,
quotas, tenant scoping). bundlemcp propagates identity two ways: selective
forwarding of client request headers, and an injected `X-MCP-User` header
carrying the resolved caller `sub`. This is the contract application-layer's upstream
servers (seo-gsc, hyperframes) already rely on.

## Requirements

- **FWD-1** Per-server `forward_headers`: a map of client-header →
  upstream-header names (commonly `authorization → authorization`). Only
  explicitly listed headers are forwarded.
- **FWD-2** Deny-list enforced at write time and at runtime: `host`,
  `content-length`, `cookie`, `x-api-key`, anything `sec-*`/`proxy-*`, and
  the `mcp-session-id` header MUST never be forwardable (metamcp's
  `DENIED_FORWARD_HEADERS`, extended).
- **FWD-3** Per-server flag `send_identity_header` (default on): inject
  `X-MCP-User: <sub>` (resolved caller — user id or `api_key:<id>`), and
  strip any client-supplied `X-MCP-User` unconditionally so it can never be
  spoofed. When the caller is anonymous (`none`-auth endpoint) the header is
  omitted.
- **FWD-4** Upstreams that need to verify the forwarded bearer can call
  `POST /oauth/introspect` ([OAS-5](20-oauth-server.md)) — the sequence
  application-layer's servers use today against metamcp.
- **FWD-5** Sessions serving requests with forwarded per-request headers MUST
  bind those headers to the upstream session correctly: an upstream
  connection carrying user A's forwarded authorization MUST never serve
  user B's request ([30-session-management.md](30-session-management.md) —
  connection reuse is keyed by identity when forwarding is active; metamcp
  solved this by bypassing idle-session reuse for such servers). The binding
  key MUST incorporate a hash of the **forwarded header values**, not just
  the resolved `sub` — the same user presenting different credentials (e.g.
  on two endpoints) gets distinct upstream bindings.

## Out of scope

- Rewriting/normalizing header values (verbatim forwarding only).
- Signed identity assertions (JWT-style) toward upstreams — `X-MCP-User` is
  trusted network-internal; if a deployment needs proof, upstreams introspect
  the forwarded bearer (FWD-4).

## Open questions

- None.
