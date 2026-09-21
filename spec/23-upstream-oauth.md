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
  **dynamic registration** against the upstream (RFC 7591) or
  **pre-registered** client id/secret entered by the admin (for providers
  without DCR). A stored client always wins. Without one, the first connect
  registers the gateway as a **public** client (`token_endpoint_auth_method:
  none`, PKCE, grants `authorization_code` + `refresh_token`, the gateway's
  callback as the only redirect URI) and stores the registration with the
  metadata it was made against; an authorization server that offers no
  registration endpoint leaves the admin to store a client. The authorization
  server is found the way the MCP authorization spec orders it: the
  `resource_metadata` a 401 from the server names in `WWW-Authenticate`, then
  the RFC 9728 document path-inserted for the server's path, then at the
  origin; its metadata through RFC 8414 (path-inserted) or OpenID Connect
  discovery. Every URL on that chain passes the egress policy
  ([SEC-1](70-security.md)).
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
  Because a user with no token may have no tool to call yet, `tools/list`
  also offers a signed-in caller who has no valid token for a `per_user`
  member server a gateway-provided tool `<server>__connect_account`
  ([ADR-0037](../docs/adr/0037-connect-account-tool.md)). Calling it returns
  the connect URL as a normal result; it reaches no upstream and is not
  metered. It is not listed once the caller holds a valid token, stays
  callable to connect a different account, and never shadows an upstream
  tool presenting the same name. API-key and anonymous callers are not
  offered it: a per-user connection is keyed by a user.
- **UPO-9 Discovery with upstream credentials:** tool discovery
  ([DISC-1](11-tool-discovery.md)) of an `upstream_oauth` server sends a
  bearer: the shared connection's for `shared` mode, any user's valid
  connection's for `per_user` mode (tool lists rarely depend on the caller,
  and without some user's token the server cannot be asked at all). With no
  connection to use, discovery reports "upstream not connected" without
  counting it toward the server's error streak
  ([SRV-4](10-server-registry.md)). A completed connect triggers discovery
  and invalidates the server's bundles, so live clients receive
  `tools/list_changed` ([BND-7](12-bundles.md)).
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
  cannot serve `per_user` upstream servers. The invariant is enforced at
  **every** mutation that could violate it: endpoint create/update, bundle
  membership changes, and switching a server's `identity_mode`.
- **UPO-7** Upstreams that verify forwarded bearers against
  `/oauth/introspect` ([FWD-4](24-identity-forwarding.md)) authenticate to it
  with their own `service`-kind API key ([KEY-2](22-api-keys.md)) provisioned
  by the admin — introspection is never anonymous ([OAS-5](20-oauth-server.md)).
- **UPO-8 Issuer validation (RFC 9207):** the connect flow records the
  upstream authorization server's `issuer` from its validated metadata in the
  single-use state before redirecting, and on callback applies the RFC 9207
  §2.4 rule: an `iss` that is present MUST equal the recorded issuer
  (string comparison, no normalisation) or the callback is rejected before the
  code is redeemed; an absent `iss` is rejected when the server's metadata
  advertises `authorization_response_iss_parameter_supported`. Stored
  credentials are bound to the issuer that granted them and are never
  presented to another authorization server.

## Out of scope

- Being an IdP or brokering identities between upstreams.
- Token sharing across bundlemcp instances that don't share the database.

## Open questions

- ~~UX detail of the per-user connect prompt (MCP elicitation vs. error message
  with URL).~~ **Resolved** ([ADR-0017](../docs/adr/0017-upstream-oauth-encryption.md)):
  a structured MCP error carrying the connect URL — reliable across clients and
  independent of a live elicitation channel. Elicitation-based connect is
  deferred (the relay already supports it, so it can be added without rework).
  Amended by [ADR-0037](../docs/adr/0037-connect-account-tool.md): the error
  stays for calls to a server's tools, and the `<server>__connect_account`
  tool is added so a user with no tools yet can still reach the URL.
