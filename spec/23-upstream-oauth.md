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
  ([SRV-1](10-server-registry.md)) needs a client identity at the upstream
  authorization server. The gateway uses the MCP authorization spec's
  priority order ([ADR-0040](../docs/adr/0040-upstream-client-identification.md)):
  1. a **pre-registered** client id/secret an admin stored — always wins;
  2. a **Client ID Metadata Document**: when the authorization server
     advertises `client_id_metadata_document_supported` and accepts `none`
     as a token endpoint auth method, the gateway's client id is the URL of
     its own published document, `{public_base}/oauth/upstream/client.json`
     (public client, PKCE, the gateway's callback as the only redirect URI) —
     nothing is registered or stored;
  3. **dynamic registration** (RFC 7591, deprecated by the MCP spec but kept
     for authorization servers without CIMD): the gateway registers as a
     public client (`token_endpoint_auth_method: none`, `application_type:
     web`, grants `authorization_code` + `refresh_token`, the callback as the
     only redirect URI) and stores the registration with the metadata and
     issuer it was made against;
  4. otherwise the connect fails with "the admin has to store a client",
     and inspection ([SRV-11](10-server-registry.md)) reports
     `preregistered_required` before anyone tries.

  The authorization server is found the way the MCP authorization spec orders it: the
  `resource_metadata` a 401 from the server names in `WWW-Authenticate`, then
  the RFC 9728 document path-inserted for the server's path, then at the
  origin; its metadata through RFC 8414 (path-inserted) or OpenID Connect
  discovery. Every URL on that chain passes the egress policy
  ([SEC-1](70-security.md)). The connect requests the scopes the **protected
  resource** asks for — the `scope` of its 401 challenge, else its resource
  document's `scopes_supported` — and no `scope` at all when it names none,
  leaving the authorization server to apply the client's defaults. Endpoints
  that were remembered or entered by an admin carry no resource scopes, so the
  resource is asked again at connect time rather than requesting nothing. The
  authorization server's own `scopes_supported` is never requested: it is the
  server's whole catalogue, and a server refuses the entire request over one
  scope the client was not granted. The challenge is obtained with an
  unauthenticated `POST` of an MCP request (`server/discover`), because a
  stateless server answers `GET` with 405 before it ever challenges.
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
  token (or, for a client-credentials client, a new grant — UPO-11), retry
  the original request once. The retry is triggered by the upstream's 401
  itself, observed on the HTTP response, not by any failed call; if refresh fails, surface a
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
- **UPO-10 Scope step-up.** A 403 with `error="insufficient_scope"` from an
  upstream on a call ([SRV-12](10-server-registry.md)) is not retried
  blindly: the challenge's `scope` is added to the scopes the server's next
  connect requests (the union with what was requested before), and the
  caller receives the structured reconnect error of UPO-4 naming the
  missing permission, so reconnecting grants it. The step-up scopes are
  stored with the server's client configuration and survive restarts.
- **UPO-11 Client credentials.** For a shared upstream that authorizes a
  machine rather than a person, an admin may store the client with
  `grant_type: client_credentials` (the MCP OAuth Client Credentials
  extension). The gateway then obtains and renews tokens with the
  `client_credentials` grant — client secret in the request body,
  `resource` and resource scopes included — without any browser connect;
  "Connect" performs the grant immediately. Such a client requires
  `identity_mode=shared`, a client secret, and an authorization server
  whose `grant_types_supported` (when advertised) includes
  `client_credentials`. JWT client assertions (RFC 7523) are not
  supported.
- **UPO-12 Resource indicators.** Every authorization request, token request
  and refresh request carries the RFC 8707 `resource` parameter: the
  protected resource document's `resource` when it is a parent of the
  server URL, otherwise the canonical server URL — whether or not the
  authorization server advertises support.
- **UPO-13 Metadata the gateway refuses.** Discovery rejects authorization
  server metadata that does not list `S256` in
  `code_challenge_methods_supported` (the connect cannot use PKCE), and
  metadata whose `issuer` differs from the issuer the document was fetched
  for. A dynamically registered client is bound to the issuer it was
  registered at: when the server's authorization server changes, the stored
  registration is discarded and the gateway registers again. An
  admin-stored client is never discarded; a connect against a different
  issuer than it was stored for is refused with a message naming both.

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
