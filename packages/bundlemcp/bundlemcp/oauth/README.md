# oauth — authentication mechanisms

bundlemcp has **four distinct authentication systems** that people routinely
conflate. They protect different surfaces, accept different credentials, and
keep their state in different places. Getting them straight is the key to
understanding this package.

| # | System | Who | Credential | Validated by | State |
|---|--------|-----|-----------|--------------|-------|
| (a) | **MCP client → endpoint** | claude.ai etc. calling `/{endpoint}/mcp` | OAuth 2.1 token (`bmcp_at_…`) **or** API key (`bmcp_sk_…`) | `gateway/mcp_endpoint/authentication/` (one authenticator per mode) | DB `oauth_access_tokens`, `api_keys` |
| (b) | **Admin browser** | a human in the web UI | OIDC session cookie `bmcp_session` | `oauth/oidc/login_controller.py` + `store/admin_sessions/` | Redis `bmcp:adminsession:{id}`, user in DB |
| (c) | **Management-API service** | scripts calling `/api/v1/*` | service-kind API key **or** admin cookie | `api/auth.py::ManagementAuth` → `services/auth_service/` | DB `api_keys` / Redis session |
| (d) | **Gateway → protected upstream** | the gateway itself | static headers / gateway-managed OAuth / forwarded caller bearer | `gateway/mcp_endpoint/upstream_credentials.py` + `oauth/upstream_client/` | DB `upstream_oauth_*` (encrypted) |

The two switches that select behavior:

- **`Endpoint.auth_modes`** (JSON list of `oauth`/`api_key`/`none`, default
  `["api_key"]`) governs how *clients* authenticate to an endpoint — system (a).
- **`McpServer.auth_mode`** (`none`/`static_headers`/`upstream_oauth`) governs
  how the *gateway* authenticates to an upstream server — system (d).

Every externally visible URL in all four systems is derived from
`settings.public_url`, never the request `Host` — see [§5](#5-the-public-url-rule).

> **"Redis" here = the RESP store, which ships as Valkey** (BSD-3; ADR-0022).
> The `bmcp:…` keys and the `redis-py` client are genuinely Redis-protocol-named
> and stay as written; the store *daemon* is Valkey. See
> [../../README.md](../../README.md#a-note-on-the-resp-store-valkey-not-redis-adr-0022).

---

## 1. MCP-client OAuth 2.1 (system a)

This is the full OAuth 2.1 authorization-server flow a remote connector like
claude.ai uses. All routes are mounted at **root** (no `/api/v1` prefix) so
`.well-known` discovery works. Controllers: `metadata_controller.py`,
`registration_controller.py`, `authorize_controller.py`, `token_controller.py`;
the protocol logic behind them is `services/oauth_server/` (ADR-0028).

### The end-to-end sequence

```
claude.ai                          gateway                         Keycloak (IdP)
   │  GET /.well-known/oauth-authorization-server  →  issuer + endpoints
   │  POST /oauth/register (DCR)                    →  client_id [+ secret once]
   │  GET /oauth/authorize?…PKCE…&resource=…/ep/mcp
   │        └─ no admin session? 302 /login ────────────────────────→ login form
   │                                              ←──── /login/callback (code)
   │        └─ consent screen (or skip if persisted)
   │  POST /oauth/consent (approve) ──────────────→  302 redirect_uri?code=…
   │  POST /oauth/token (code + PKCE verifier)     →  access_token + refresh_token
   │  POST /{ep}/mcp  Authorization: Bearer bmcp_at_…   (audience-checked)
```

### Discovery — `metadata_controller.py`

- `GET /.well-known/oauth-authorization-server` advertises the issuer and
  endpoint URLs, `code` response type, `authorization_code`+`refresh_token`
  grants, `S256` PKCE, and scope `mcp`.
- `GET /.well-known/oauth-protected-resource/{endpoint}/mcp` (RFC 9728) is the
  per-endpoint resource metadata that the `401 WWW-Authenticate` challenge points
  clients at. 404 if the endpoint is missing or disabled.

### Dynamic client registration — `registration_controller.py`

`POST /oauth/register` (201). Rate-limited per IP (10 / hour, fails open).
Redirect URIs must be `https` (or `http` only for localhost). Mints
`client_id = bmcp_client_…`; for confidential clients a `client_secret` is
generated, **hashed** into `OAuthClient.client_secret_hash`, and the plaintext
returned exactly once (DOM-3). Row lands in `oauth_clients`.

### Authorize — `authorize_controller.py` + `AuthorizationService`

`GET /oauth/authorize` validates in order (client errors are 400 and never
redirect; protocol errors redirect with `error=`):

1. Known `client_id`; `redirect_uri` in the client's registered list.
2. `response_type == code`.
3. **PKCE is mandatory** — `code_challenge` present, method `S256`.
4. **Audience (RFC 8707):** the `resource` param must resolve to one of *our*
   endpoints, which must be enabled and have `oauth` in its `auth_modes`.
5. **Login bounce:** if there's no admin browser session, 302 to
   `/login?next=<return url>`, where the return URL is rebuilt from `public_url`
   (not the incoming Host — see §5; this is the reverse-proxy fix).
6. **Persisted-consent skip (OAS-11):** if an un-revoked `OAuthConsent` row
   already exists for `(user, client, endpoint)`, issue a code immediately with
   no screen.
7. Otherwise store a single-use consent token in Redis
   (`bmcp:pendingconsent:{token}`, 600s) and render `consent.html` (hardened
   headers: strict CSP, `X-Frame-Options: DENY`, `no-store`).

### Consent → code — `POST /oauth/consent`, `_issue_code`

The consent POST reads-and-deletes the single-use Redis token (400 if expired),
re-checks the session user matches, writes the `oauth_consents` row on approve,
and issues a code. The code is `token_urlsafe(32)`; only its **SHA-256 hash** is
stored (`oauth_authorization_codes`, PK = hash, OAS-8), alongside the PKCE
challenge, the endpoint audience, and a 10-minute expiry.

> Operational note learned the hard way: the consent token is single-use, so a
> double-submitted approve returns "consent request expired." And behind a proxy
> the login bounce **must** rebuild `next` from `public_url` or the flow
> dead-ends at `/` after login — that's exactly what the DEP-1 comment in
> `authorize_controller.py` guards.

### Token — `token_controller.py` + `OAuthTokenService`

`POST /oauth/token`. Client auth (`OAuthClientAuthenticator`): public clients send
`client_id`; confidential clients send the secret (HTTP Basic or form) compared
constant-time against the stored hash. Client-auth failures feed the per-IP
auth-failure limiter.

- **`authorization_code`** (`AuthorizationCodeGrant`): look up the code by hash; reject if used, wrong
  client, or expired. Verify PKCE (`base64url(sha256(verifier)) == code_challenge`).
  Mark the code used (single-use). Issue a token pair.
- **`refresh_token`** (`RefreshTokenGrant`): look up by refresh-token hash; reject if revoked/expired/
  wrong client. **Rotate**: revoke the old row, issue a new pair.
- **`TokenIssuer`:** `access = bmcp_at_…` (1h), `refresh = bmcp_rt_…` (7d). Both
  stored only as SHA-256 hashes in `oauth_access_tokens`, tagged with the
  `endpoint_id` audience and scope. Response is `no-store`.

### Introspection, revocation, purge

- **`POST /oauth/introspect` (RFC 7662)** requires a **service** API key —
  accepted as a bearer/`X-API-Key`, or as the HTTP Basic *password* (the "client
  credentials" form ultra-mcp's upstreams use). It returns the standard
  `{active, sub, client_id, scope, exp, aud, email}` for a valid OAuth token.
  Two special cases matter for upstream auth (system d):
  - A forwarded **gateway API key** presented as the token introspects as
    `{"active": true, "sub": "api_key:<id>", "token_use": "api_key"}` (FWD-4), so
    an introspecting upstream can serve API-key callers.
  - This is what makes the seo-gsc pattern work — see [§4](#4-gateway--protected-upstream-system-d).
- **`POST /oauth/revoke` (RFC 7009)** authenticates the client like the token
  endpoint (RFC 7009 §2.1; a public client by `client_id` alone) and flips
  `revoked` on a matching access or refresh token issued to that client;
  always 200 for an unknown or foreign token, 401 (counted toward the RATE-5
  lockout) for a client that cannot authenticate.
- **`TokenPurgeService`**, run by `TokenPurger` from the composition root, deletes
  expired codes, long-dead refresh rows, and never-used stale clients (SEC-8).

### The MCP edge's own validation

Note that `OAuthBearerAuthenticator` (via `AuthService.authenticate_oauth_bearer`) validates presented access
tokens with a **direct DB read** (hash lookup + revoked/expiry/**audience**
check), independently of `introspect`. The two paths must stay in sync; the
audience check (`row.endpoint_id == view.endpoint.id`) is what makes a token
endpoint-bound (EP-3a).

---

## 2. Admin OIDC login (system b)

Files: `oidc/login_controller.py`, `oidc/jose_oidc_provider.py`,
`store/admin_sessions/`. The gateway is an OIDC *relying party* in
front of an external IdP (Keycloak in dev); it does not manage passwords.

- **`GET /login?next=`** generates a `nonce` and parks it with `next` as an
  `OidcLoginState` in a `SingleUseState` (Redis `bmcp:oidcstate:{state}`, 600s,
  read-once), then redirects to the IdP. `next` is clamped by
  `clamp_post_login_redirect` — only a relative `/path` or a `public_url`/
  `web_origins` URL is honored, everything else falls back to `/` (open-redirect
  guard).
- **`GET /login/callback?code&state`** reads-and-deletes the state (CSRF),
  exchanges the code (the provider validates the ID token against JWKS and checks
  the `nonce`), then `UserProvisioningService.provision`.
- **`provision`** is create-or-update by `(oidc_issuer, oidc_sub)`. It
  refreshes `email`, `display_name`, and **`is_admin` on every login** (ADM-3) —
  `is_admin` is true if the email is in `admin_emails` or the token carries a
  `bundlemcp-admin` group. So revoking someone's admin email demotes them at
  their next login, not at some cache expiry.
- A session is created and the **`bmcp_session`** cookie set: `httponly`,
  `samesite=lax`, `secure` iff `public_url` is https, `max_age` 12h (forces
  periodic re-login, ADM-6). The session record (Redis `bmcp:adminsession:{id}`,
  12h TTL) holds `user_id`/`email`/`is_admin`, but `is_admin`/`is_active` are
  **re-checked against the DB on every use**, so deactivation takes effect
  immediately.
- **`POST /logout`** deletes the session and clears the cookie.

---

## 3. Management-API auth (system c)

Files: `api/auth.py`, `services/auth_service/`, `api/controllers/me_controller.py`.

`ManagementAuth` (attached once to `ManagementController`, so every `/api/v1` route inherits it)
accepts **either** an admin cookie **or** a service-kind API key:

1. **Admin cookie** → `AuthService.admin_principal`. For any state-changing
   method it *also* enforces the **CSRF Origin/Referer check (SEC-4)**: the
   `Origin`/`Referer` must match `public_url` or an allowlisted `web_origin`,
   else 403. (`SameSite=Lax` cookies plus this origin check is the CSRF defense;
   non-browser callers use keys instead.)
2. **API key** (`Authorization: Bearer` / `X-API-Key`, never query params) →
   must be `kind == service`. A non-service key is a deliberate 403 ("key is not
   service-kind", KEY-2).
3. Otherwise 401.

`AuthService` is framework-free (it takes header/cookie strings and a DB
session, never a FastAPI `Request`) so the same logic is reused by the MCP edge
and the token endpoint. `Principal` is `{kind: "admin"|"service", user_id,
api_key_id}`.

`GET /api/v1/me` is the exception that answers for **any** active session,
admin or not — the web app calls it to decide between the app and the "no
access" page (UI-2). It reports `kind` `admin`/`user`/`service`.

CORS for the management API is credentials-enabled and restricted to exactly
`settings.web_origins`.

---

## 4. Gateway → protected upstream (system d)

When a bundled MCP server is itself protected, the gateway needs to present a
credential upstream. There are three patterns, selected by `McpServer.auth_mode`
and its `forward_headers`.

### (i) Static headers

`auth_mode = static_headers` with a `static_headers` map (e.g.
`Authorization: Bearer <static token>`). The values are write-only through the
API (only header *names* are ever returned, SRV-3) and merged into every upstream
request. Simplest case; no per-user identity.

### (ii) Gateway-managed upstream OAuth

`auth_mode = upstream_oauth`. The gateway is an OAuth client *of the upstream*
and stores the resulting tokens **encrypted at rest**. Files:
`upstream_connect_controller.py`, `upstream_client/`, `../crypto/`.

- **Connect flow:** `GET /oauth/upstream/{server}/connect` (optionally `?as=me`
  for a per-user connection). Requires a signed-in user (bounces to `/login`
  otherwise) and encryption keys (503 otherwise). A *shared* connection needs an
  admin and is rejected for a `per_user` server; `?as=me` binds the token to the
  user. It builds a PKCE authorize URL (`UpstreamConnectFlow`), parks an
  `UpstreamConnectState` in a `SingleUseState` (Redis `bmcp:upstream-connect:{state}`,
  600s, read-once), and redirects to the upstream IdP. The
  callback (`/oauth/upstream/callback`) exchanges the code and saves the encrypted
  token.
- **Token store (`UpstreamTokenStore`, a facade over `UpstreamTokenRepository`,
  `UpstreamConnectFlow` and `UpstreamTokenRefresher`):** keyed `(server_id, user_id)` with
  `user_id NULL = shared` (UPO-2). Tokens live in `upstream_oauth_tokens`
  (Fernet-encrypted JSON), client config in `upstream_oauth_clients`.
  `ensure_access_token` returns a valid bearer, refreshing proactively near
  expiry or on demand (`force=True`) after an upstream 401. Refreshes are
  single-flighted with a Redis lock so concurrent calls don't stampede the token
  endpoint.
- **Identity modes:** `shared` (one token an admin establishes) vs `per_user`
  (a token per user; the caller must be an authenticated MCP user at call time).
  UPO-6 forbids exposing a `per_user` upstream through a `none`-auth endpoint,
  since there'd be no identity to key the token on.
- **Encryption (`crypto.py`):** Fernet (AES-128-CBC + HMAC) via `MultiFernet`.
  Keys come from `BUNDLEMCP_TOKEN_ENCRYPTION_KEYS`; the **first key encrypts, all
  keys decrypt**, so keys rotate without a migration (DEP-9). Decryption fails
  closed. With no keys configured, upstream OAuth is disabled entirely
  (`app.state.upstream_tokens = None`).
- **Runtime (`mcp_endpoint._handle_call`):** the upstream bearer is resolved
  *before* metering (an unconnected upstream returns a "connect at …" error and
  is never billed), injected as `Authorization`, and merged so it wins over any
  forwarded header. A single reactive retry on upstream 401 force-refreshes and
  replays without re-metering (UPO-4/MID-3).

### (iii) Forwarded caller bearer + upstream introspection (the seo-gsc pattern)

Some upstreams (like `seo-gsc`) run their *own* OAuth and just want to know who
the caller is. Here the server is `none`/`static_headers` with
`forward_headers: {authorization: authorization}`. `_forward_headers` passes the
caller's bearer through (`authorization` is not on the deny-list), and the
upstream calls **our** `POST /oauth/introspect` (with a service key) to resolve
it — getting back the OAuth `sub`, or `api_key:<id>` for API-key callers (FWD-1/
FWD-4). The upstream then maps that `sub` to its own per-user state (e.g. a
stored Google token). Identity forwarding via `X-MCP-User` (FWD-3) is the
lighter-weight sibling: the gateway injects a trusted `X-MCP-User: <sub>` header
and strips any client-supplied one.

---

## 5. The public-URL rule

`urls.py` is tiny but load-bearing. **Every externally visible URL derives from
`settings.public_url` (`BUNDLEMCP_PUBLIC_URL`), never the incoming `Host`
header.**

- `issuer(settings)` — the OAuth issuer string.
- `endpoint_resource(settings, name)` — the `{issuer}/{name}/mcp` RFC 8707
  audience / RFC 9728 resource id.
- `endpoint_name_from_resource` — the reverse check that a `resource` param
  belongs to this deployment.

Behind a reverse proxy (or a dev tunnel), `request.url`/`Host` is the *internal*
origin — something the browser can't navigate back to and that the login
`next`-clamp would reject. Trusting it silently breaks the OAuth handshake. So
the rule is applied consistently: metadata documents, the `401 WWW-Authenticate`
challenge, the authorize→login bounce, the OIDC redirect URI and `_safe_next`
allowlist, the upstream-connect redirect URI, the "connect here" hints, and the
management-API CSRF allowlist all go through `public_url`.

---

## Credential formats & storage (quick reference)

| Credential | Format | Stored as | TTL |
|-----------|--------|-----------|-----|
| API key | `bmcp_sk_` + `token_urlsafe(32)` | SHA-256 hash + display prefix | none (deactivatable) |
| OAuth access token | `bmcp_at_…` | SHA-256 hash, endpoint-bound | 1h |
| OAuth refresh token | `bmcp_rt_…` | SHA-256 hash | 7d, rotated on use |
| Authorization code | `token_urlsafe(32)` | SHA-256 hash (PK) | 10min, single-use |
| OAuth client secret | `token_urlsafe(32)` | SHA-256 hash | until purge |
| Admin session | `token_urlsafe(32)` id | Redis JSON, cookie `bmcp_session` | 12h |
| Upstream OAuth token | provider-issued | Fernet-encrypted JSON | provider expiry, auto-refresh |

Nothing reversible is stored for gateway-issued credentials — only hashes.
Upstream tokens are the sole secret held in a recoverable form, and those are
encrypted with rotating keys and never logged or returned (DOM-3, spec 51).

---

## File index

| File | Responsibility |
|------|----------------|
| `metadata_controller.py` | `.well-known` discovery (auth-server + protected-resource) |
| `registration_controller.py` | Dynamic client registration (`POST /oauth/register`) |
| `authorize_controller.py` | `/oauth/authorize` + `/oauth/consent`; the consent page |
| `token_controller.py` | `/oauth/token`, `/oauth/introspect`, `/oauth/revoke` |
| `token_purger.py` | Periodic sweep of expired codes, tokens and stale clients |
| `oauth_error_response.py` | Renders `OAuthError` / `AuthorizationRedirectError` in RFC shape |
| `oidc/login_controller.py` | Admin OIDC login: `/login`, `/login/callback`, `/logout` |
| `oidc/jose_oidc_provider.py` | The real IdP, built from its discovery document |
| `session_cookie.py` | The `bmcp_session` cookie name and attributes |
| `upstream_connect_controller.py` | Upstream OAuth connect flow (`/oauth/upstream/…`) |
| `upstream_client/` | `UpstreamTokenStore` and the repository, connect flow and refresher behind it |
| `providers.py` | FastAPI providers for oauth-owned collaborators and the OAuth services |
| `urls.py` | The endpoint resource identifier (§5) |
| `../services/oauth_server/` | Grants, token issuance, authorization, registration, provisioning, purge |
| `../store/admin_sessions/` | `AdminSessionStore` — the Redis-backed browser session |
| `../store/single_use_state.py` | `SingleUseState[T]` — typed, read-once browser round-trip state |
| `../api/auth.py` | `ManagementAuth` — the management-API auth edge (§3) |
| `../services/auth_service/` | `AuthService`, `AdminSessionService`, `Principal` |
| `../crypto/` | Token hashing, PKCE, and `TokenCipher` for encryption at rest |
