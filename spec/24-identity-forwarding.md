# 24 — Identity & header forwarding

**Status:** Accepted · **Origin:** metamcp carry-over (fork feature `forward_headers` + the first consumer's identity contract)
**Prior art:** `../metamcp/apps/backend/src/lib/metamcp/header-forwarding.ts`, the first consumer's compose stack (seo-gsc/hyperframes identity contract)

## Summary

Upstream servers often need to know **who** is calling (per-user storage,
quotas, tenant scoping). bundlemcp propagates identity two ways: selective
forwarding of client request headers, and an injected `X-MCP-User` header
carrying the resolved caller `sub`. This is the contract the first consumer's upstream
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
  the first consumer's servers use today against metamcp.
- **FWD-5** Sessions serving requests with forwarded per-request headers MUST
  bind those headers to the upstream session correctly: an upstream
  connection carrying user A's forwarded authorization MUST never serve
  user B's request ([30-session-management.md](30-session-management.md) —
  connection reuse is keyed by identity when forwarding is active; metamcp
  solved this by bypassing idle-session reuse for such servers). The binding
  key MUST incorporate a hash of the **forwarded header values**, not just
  the resolved `sub` — the same user presenting different credentials (e.g.
  on two endpoints) gets distinct upstream bindings.

- **FWD-6 Delegated tokens (token exchange).** A server with
  `auth_mode=delegated_token` ([SRV-1](10-server-registry.md)) receives,
  instead of the caller's own bearer, a short-lived token the gateway issues
  for the caller with that **server as its audience**
  ([ADR-0041](../docs/adr/0041-delegated-upstream-tokens.md)) — the RFC 8693
  token-exchange model (subject: the caller's authenticated identity;
  audience: the upstream), performed inside the gateway. The token is sent
  as `Authorization: Bearer`, is minted afresh for every upstream request
  (only its hash is kept, never the value), is valid for five minutes, and
  lives in Valkey only (a restart of any replica does not invalidate it).
  Introspection ([OAS-5](20-oauth-server.md)) reports it `active` with the
  caller's `sub` (user id or `api_key:<id>`), `aud` = the server's URL,
  `client_id` = the gateway's own delegation client, `token_use` =
  `delegated`, and `act.sub` = the endpoint the caller came through. An
  anonymous caller gets no token. Tool discovery has no caller; it sends
  the server's static headers as for any other server.
- **FWD-7 Passthrough is labelled, not hidden.** A `forward_headers` entry
  that forwards `authorization` passes the caller's gateway token to the
  upstream — token passthrough, which the MCP authorization spec forbids an
  MCP server to accept. It remains supported for trusted internal upstreams
  that introspect it (FWD-4), but the API reports it as
  `forwards_caller_token: true` and the UI shows it as passthrough with
  `delegated_token` as the conformant alternative.

## Out of scope

- Rewriting/normalizing header values (verbatim forwarding only).
- Signed identity assertions (JWT-style) toward upstreams — `X-MCP-User` is
  trusted network-internal; if a deployment needs proof, upstreams introspect
  the delegated token (FWD-6) or, for legacy setups, the forwarded bearer
  (FWD-4).
- Exchanging the caller's token at a *third-party* authorization server
  (RFC 8693 against the upstream's own AS, Entra OBO, ID-JAG): no targeted
  upstream trusts bundlemcp as a subject-token issuer.

## Open questions

- None.
