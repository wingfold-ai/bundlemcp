# 23 — Upstream OAuth (bundlemcp as OAuth client)

**Status:** Accepted · **Origin:** improvement (metamcp stored ONE token set per server; bundlemcp stores per-(server, user))
**Prior art:** `../metamcp/apps/backend/src/lib/oauth-upstream/`, `oauth_sessions` table, `../metamcp/apps/backend/src/trpc/pre-registered-oauth.ts`

## Summary

Some upstream MCP servers are themselves OAuth-protected (Linear, Notion,
Salesforce-style). bundlemcp performs the OAuth dance against them, stores
tokens, refreshes on 401, and — unlike metamcp — can hold tokens **per end
user**, so users of an endpoint each act with their own upstream identity
instead of sharing one credential.

## Requirements

- **UPO-1** A server with `auth_mode=upstream_oauth`
  ([SRV-1](10-server-registry.md)) gets upstream OAuth client config: either
  **dynamic registration** against the upstream (RFC 7591, discovered via its
  401/`.well-known` chain) or **pre-registered** client id/secret entered by
  the admin (for providers without DCR).
- **UPO-2** Token storage is keyed `(server_id, user_id)`; `user_id = NULL` is
  the **shared/service connection** established by an admin from the UI.
  Per-server setting `identity_mode`: `shared` (all callers use the NULL row —
  metamcp behavior) or `per_user` (each caller must connect their own
  account).
- **UPO-3** Interactive connect flow: from the server detail page (admin,
  shared mode) — and, for `per_user` mode, from a minimal hosted "connect your
  account" page a user is directed to when calling a tool that lacks a token
  for them. State parameter is server-generated, single-use, stored
  server-side (metamcp's CSRF fix carried over). PKCE used when supported.
- **UPO-4** On upstream 401/token-expiry: refresh with the stored refresh
  token, retry the original request once; if refresh fails, surface a
  structured MCP error telling the caller (or admin) to re-connect, and mark
  the token row invalid. Refresh must be single-flight per token row
  (Redis lock) to avoid stampedes.
- **UPO-5** Tokens are encrypted at rest ([DOM-3](02-domain-model.md)), never
  logged, never returned by any API. The UI shows connection status
  (connected/expired/error + account hint) only.
- **UPO-6** `per_user` calls MUST resolve the caller identity from the request
  context ([EP-6](14-endpoints.md)); an unauthenticated (`none`-auth) endpoint
  cannot serve `per_user` upstream servers — validated at endpoint creation.

## Out of scope

- Being an IdP or brokering identities between upstreams.
- Token sharing across bundlemcp instances that don't share the database.

## Open questions

- UX detail of the per-user connect prompt (MCP elicitation vs. error message
  with URL) — decide against real client behavior during implementation.
