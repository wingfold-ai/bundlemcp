# Implementation guide — offloading the OAuth server to library code

**Status:** proposed · **Author:** —  · **Supersedes in part:** [ADR-0014](adr/0014-gateway-rendered-oauth-authlib.md) · **Extends:** [ADR-0028](adr/0028-oauth-server-as-services.md)

This guide is the implementation plan for replacing bundlemcp's hand-written
OAuth 2.1 protocol plumbing with library code, keeping only the parts that
encode bundlemcp's own product decisions.

It is written to be executed **in order**. Each phase is independently
shippable and independently revertable. Phases 0 and 1 are prerequisites for
phase 2 and are worth doing even if phase 2 is never started.

---

## 0. Executive summary

| | |
|---|---|
| **Dependency removed** | `authlib>=1.6` (direct) |
| **Dependencies added** | `mcp>=2.1`, `joserfc>=1.7` — **both already installed transitively** |
| **Net installed-package delta** | **zero wheels** |
| **Protocol code deleted** | ≈ 220 LOC |
| **Security defects fixed** | 4 (one HIGH, one HIGH, two MEDIUM) |
| **Specced-but-missing requirements closed** | OAS-13, OAS-14 |
| **New ADRs required** | 2 (`0031`, `0032`) |

### The headline finding

**Authlib's authorization-server framework cannot be used by bundlemcp.** This
is structural, not a matter of effort:

- `grep -rn "async def" authlib/oauth2/` returns **zero matches**. Every
  authorization-server hook — `AuthorizationServer.query_client`, `save_token`,
  `AuthorizationCodeGrant.save_authorization_code`, `query_authorization_code`,
  `authenticate_user` — is `def`, not `async def`.
- `authlib/integrations/` ships `flask_oauth2` and `django_oauth2` only.
  There is no Starlette/FastAPI authorization-server integration.
  `authlib.integrations.starlette_client` is a *login-with-X client registry*.
- `rfc8414` and `rfc9207` are `dict` subclasses for **validating** someone
  else's metadata, not for generating yours.

Driving those sync hooks from an asyncpg + async-SQLModel codebase means
`run_in_threadpool` around every DB call or a greenlet bridge — fighting both
the `UnitOfWork`/`Repository` shape ([ADR-0025](adr/0025-repository-unit-of-work-and-container.md))
and the replica-agnostic state model ([ADR-0004](adr/0004-postgres-redis-state-split.md)).

**The framework that does fit is `mcp.server.auth`**, from the MCP Python SDK —
already installed, because `fastmcp[client,server]==4.0.3` requires `mcp>=2.0.0`.

### Why the MCP SDK wins

Verified against the installed `mcp 2.1.1`:

1. `OAuthAuthorizationServerProvider` (`mcp/server/auth/provider.py:137`) is a
   `Protocol` with **ten `async def` hooks**: `get_client` (`:138`),
   `register_client` (`:151`), `authorize` (`:164`),
   `load_authorization_code` (`:207`), `exchange_authorization_code` (`:221`),
   `load_refresh_token` (`:238`), `exchange_refresh_token` (`:250`),
   `load_access_token` (`:273`), `revoke_token` (`:283`),
   `exchange_identity_assertion` (`:299`). That is the `UnitOfWork`-shaped
   service boundary this repo already uses, in async.
2. Its models are Pydantic `BaseModel`s (`AuthorizationParams`,
   `AuthorizationCode`, `RefreshToken`, `AccessToken`), so the
   "Pydantic everywhere, no dataclasses" rule holds unmodified for
   *bundlemcp's* code.
3. **RFC 8707 `resource` is a first-class field** on `AuthorizationParams:16`,
   `AuthorizationCode` and `AccessToken`, with `invalid_target` in the error
   literals. The endpoint-bound audience — bundlemcp's most unusual
   requirement ([ADR-0009](adr/0009-endpoint-bound-tokens-consent.md), OAS-10) —
   is the piece that maps most cleanly.
4. **`mcp/server/auth/provider.py` imports no Starlette.** Its imports are
   `dataclasses`, `typing`, `urllib.parse`, `pydantic`, `mcp.shared.auth`.
   The provider implementation may therefore live in `services/` without
   breaking the framework-free import contract
   ([ADR-0023](adr/0023-import-contracts-and-shared-providers.md)).
   *Only the handler classes import Starlette.*

### The critical design constraint

**Use the SDK's handler classes; do not use its `create_auth_routes()` factory.**

`create_auth_routes()` (`mcp/server/auth/routes.py:75`) hardcodes
`/authorize`, `/token`, `/register`, `/revoke` at the application root and
bakes the metadata document at build time. bundlemcp needs its own paths, its
own metadata (OAS-13/OAS-14 flags the SDK has no field for), and a
**per-endpoint** RFC 9728 route rather than a single server-wide one.

Instead, instantiate `AuthorizationHandler(provider)`,
`TokenHandler(provider, client_authenticator)` and `RevocationHandler(...)`
and delegate to their `.handle(request)` from thin `Controller` methods at the
existing `/oauth/*` paths. This preserves
[ADR-0026](adr/0026-controllers.md), the metadata document, and every URL
clients have already discovered.

---

## 1. Scope: what moves, what stays

### Moves to library code

| Concern | Replaced by |
|---|---|
| RFC 6749 §4.1.1 authorization-request parsing | `AuthorizationHandler` (`handlers/authorize.py:67`) |
| RFC 6749 §3.2 token-request parsing and grant dispatch | `TokenHandler` (`handlers/token.py:84`) |
| RFC 7636 PKCE S256 verification | `TokenHandler` (`handlers/token.py:186-189`) |
| HTTP Basic / `client_secret_post` decoding | `ClientAuthenticator` (`middleware/client_auth.py:19`) |
| RFC 7009 revocation-request parsing | `RevocationHandler` (`handlers/revoke.py:32`) |
| RFC 6749 §5.2 / §4.1.2.1 error shapes | SDK handler responses |
| OAS-13 Client ID Metadata Documents (unbuilt) | `fastmcp/server/auth/cimd.py` `CIMDFetcher` |
| ID-token JOSE verification | `joserfc` |

### Stays hand-written — and why

| Kept | Reason it cannot be delegated |
|---|---|
| `introspection_service.py` (46) + `token_controller.py:70-92` | **RFC 7662 authorization-server side exists nowhere in async Python.** The SDK pins `introspection_endpoint=None` in its metadata; `fastmcp/server/auth/providers/introspection.py:45` is a *client* of someone else's introspection endpoint. Plus OAS-5's `aud` and the FWD-4 `sub: api_key:<id>` branch are bundlemcp semantics. |
| `metadata_controller.py` (35) + `schemas/oauth/authorization_server_metadata.py` | SDK's `build_metadata` hardcodes root paths, has no field for OAS-13/OAS-14, and models one resource — bundlemcp serves one RFC 9728 document **per endpoint row**. |
| `authorization_service.py:91-109`, `OAuthConsent`, `templates/consent.html` | OAS-11 persistent, revocable, per-`(user, client, endpoint)` consent with a management-API revocation path. No library models it; FastMCP's `ConsentMixin` is cookie-based and a different product decision. |
| `token_issuer.py` (43) | Opaque `bmcp_at_`/`bmcp_rt_` tokens with hashed storage and an endpoint audience (OAS-4/OAS-7/OAS-8/DOM-3). Every library alternative pushes JWTs. |
| `gateway/mcp_endpoint/authentication/` (170) | Resource-server admission with per-endpoint `auth_modes` precedence. Outside the authorization-server role; OAS-7 direct-DB validation is a deliberate ADR-0014 decision. |
| `oauth/oidc/login_controller.py` (101), `store/admin_sessions/` | bundlemcp as OIDC **relying party** for the human operator (spec 21). Orthogonal to the AS role. Only the JOSE call inside changes. |
| `oauth/upstream_client/` (621) | Multi-tenant encrypted upstream tokens keyed `(server_id, user_id)` plus a Valkey `SET NX` single-flight refresh lock. `mcp.client.auth`'s `TokenStorage` protocol **has no user key** — structurally incapable. |
| `token_purger.py`, `token_purge_service.py` (80) | OAS-8/SEC-8 storage lifecycle. |
| `registration_controller.py:27-32`, `token_controller.py:54-62` | OAS-12 DCR rate limit, RATE-5 auth-failure guard. |
| `urls.py`, `page_headers.py`, `session_cookie.py`, `post_login_redirect.py` | DEP-1 public-URL rule, SEC-6 headers, cookie policy, open-redirect clamp. |

---

## Phase 0 — Drop Authlib, adopt joserfc, fix ID-token claim validation

**Effort:** ~1 hour · **Risk:** low, but contains the single highest-severity
line in the plan · **Depends on:** nothing · **Ship independently:** yes

### Why now, independently of everything else

`authlib.jose` is **deprecated and scheduled for removal**:

```
authlib/jose/__init__.py:33
deprecate("authlib.jose module is deprecated, please use joserfc instead.", version="2.0.0")
```

bundlemcp's *entire* Authlib usage is one import at
`packages/bundlemcp/bundlemcp/oauth/oidc/authlib_oidc_provider.py:7` and two
calls at `:58-59`. That import emits a deprecation warning today and becomes an
`ImportError` at Authlib 2.0. Authlib 1.7.2 already depends on `joserfc>=1.6.0`
and delegates key handling to it, so `joserfc 1.7.2` is **already in the
lockfile** — pulled in by both `authlib` and `fastmcp-slim[server]`.

### SECURITY — fix `aud` and `iss` validation in the same change (HIGH)

The current code is:

```python
# oauth/oidc/authlib_oidc_provider.py:58-59
claims = jwt.decode(id_token, jwks_response.json())
claims.validate()
```

No `claims_options` and no `claims_cls` are passed. In
`authlib/jose/rfc7519/claims.py:105-120`, `validate_iss()` and `validate_aud()`
delegate to `_validate_claim_value()`, which **returns immediately when no
option is configured** (`:62-64`). So `validate()` today checks the signature
plus `exp`/`nbf`/`iat` — and nothing else.

The consequences are concrete:

- `aud` is never compared to `settings.oidc_client_id`.
- `iss` is never compared to the discovery document's `issuer` — yet
  `:63` reads `claims["iss"]` straight from the token and
  `user_provisioning_service.py:37` keys the local `User` identity on it.

On a shared IdP realm — which is exactly ultra-mcp's Keycloak deployment — an
ID token minted for a **different client of the same realm** satisfies every
check currently performed. OIDC Core §3.1.3.7 steps 3–4 require both. The JWKS
pin and the `nonce` check (`:60-61`) are real mitigations but do not close this.

> **This is not a regression introduced by the migration — it exists today.**
> It is called out here because phase 0 is the moment the code is open, and
> because `joserfc` makes the omission *louder*: it does not validate claims
> implicitly at all.

### Changes

**1. `packages/bundlemcp/pyproject.toml`**

```diff
-    "authlib>=1.6",
+    "joserfc>=1.7",
```

Note the removed floor was already wrong: `fastmcp` requires
`authlib>=1.6.11`, so the declared `>=1.6` never governed what resolved.

**2. Rename the module and class** (module-naming rule: a module is named for
what it holds, and it no longer holds Authlib):

| From | To |
|---|---|
| `oauth/oidc/authlib_oidc_provider.py` | `oauth/oidc/jose_oidc_provider.py` |
| `class AuthlibOidcProvider` | `class JoseOidcProvider` |

Update the three referents: `oauth/oidc/build_provider.py:1`,
`oauth/oidc/__init__.py:7` and its `__all__` entry at `:14`.

**3. Rewrite the verification block.** Replace `:7` and `:58-59`:

```python
from joserfc import jwt
from joserfc.jwk import KeySet

# ... inside exchange(), replacing lines 58-59:
key_set = KeySet.import_key_set(jwks_response.json())
token = jwt.decode(id_token, key_set)

# joserfc does NOT validate claims implicitly — this registry is the whole
# point of the change. OIDC Core 3.1.3.7 steps 3-4 require iss and aud.
claims_registry = jwt.JWTClaimsRegistry(
    iss={"essential": True, "value": self._metadata["issuer"]},
    aud={"essential": True, "value": self._settings.oidc_client_id},
    exp={"essential": True},
)
claims_registry.validate(token.claims)

claims = token.claims
```

The rest of `exchange()` — the `nonce` check at `:60-61` and the `OidcClaims`
construction at `:62-68` — is unchanged.

### What must NOT change

The `OidcProvider` Protocol (`oauth/oidc/oidc_provider.py`), the discovery
fetch (`:22-29`), `authorize_url` (`:31-40`), the nonce check, and the
`OidcClaims` mapping. The Protocol is `@runtime_checkable`, so the rename is
invisible to `build_provider` and to the composition root.

### Tests

**`tests/test_oidc.py` needs no change to pass** — and that is the problem.
It injects a `FakeOidcProvider` at `:25`, so **real JWT decoding is never
exercised by any test in the suite.**

Add before shipping, in `tests/test_oidc.py`:

1. `test_id_token_decoded_and_claims_validated` — generate an RSA keypair, sign
   an id_token, serve the JWKS from a stub, assert the claims round-trip.
2. `test_id_token_wrong_audience_rejected` (ADM-* / OIDC Core §3.1.3.7) — an
   id_token whose `aud` is a *different* client of the same issuer must raise.
   **This test fails against today's code**, which is the point.
3. `test_id_token_wrong_issuer_rejected`.
4. `test_id_token_expired_rejected`.

### What could break

- **Forgetting the claims registry.** `joserfc.jwt.decode` verifies the
  signature and nothing else. Ship without `JWTClaimsRegistry` and you have
  *removed* the `exp` check that Authlib's `claims.validate()` was doing —
  strictly worse than today.
- `KeySet.import_key_set` expects the raw JWKS dict; passing
  `jwks_response.json()["keys"]` fails.
- An IdP whose `aud` is a **list** containing the client id: `{"value": ...}`
  handles the common case; confirm against your Keycloak realm before shipping.

---

## Phase 1 — Security hardening before the refactor

**Effort:** ~half a day · **Risk:** low · **Depends on:** nothing ·
**Ship independently:** yes

These are pre-existing defects. Fix them **before** phase 2 so that a
regression during the refactor is unambiguous — you are not simultaneously
changing behaviour and structure.

### SEC-2 (HIGH) — upstream OAuth discovery bypasses the egress policy and follows a remote-controlled URL

`gateway/egress.py:42` `check_url_allowed` is imported in exactly **one** place
in the entire codebase: `gateway/upstream.py:13`. It is not applied in the
upstream OAuth path, where:

| Line | What happens |
|---|---|
| `oauth/upstream_client/httpx_upstream_provider.py:26,29` | fetches `{origin}/.well-known/...` from an admin-supplied server URL — spec 70 SEC-1 names "upstream OAuth discovery (UPO-1)" explicitly |
| `:34-36` | follows **`data["authorization_servers"][0]`** — a URL supplied by the *remote upstream* — with no origin or issuer check |
| `:109-110` | **POSTs the gateway's `client_secret`** (`:107-108`) to `meta.token_endpoint`, taken from that same remote document |

A malicious or compromised upstream MCP server can therefore exfiltrate the
gateway's pre-registered upstream client secret by pointing
`authorization_servers[0]` at an attacker-controlled host, and can reach
internal addresses through the discovery fetch (SSRF).

**Fix:**
1. Call `check_url_allowed(...)` before **every** outbound request in
   `httpx_upstream_provider.py` — lines 26, 29, 34-36 and 109-110.
2. Implement **UPO-8** (specced, unimplemented): record the discovered `issuer`
   in `UpstreamConnectState` (which today has no `issuer` field,
   `oauth/upstream_connect_state.py`) and verify it on callback
   (`upstream_connect_controller.py:112-124` performs no `iss` check).
3. Constrain `authorization_servers[0]` to the same origin as the upstream
   server URL unless an operator has explicitly configured otherwise.

`oauth/oidc/jose_oidc_provider.py:26,43,56` has the same missing egress check,
but against **operator-configured** URLs — lower severity, same one-line fix.

### SEC-5 (MEDIUM) — authorization-code and refresh-token replay race

`services/oauth_server/authorization_code_grant.py`:

```python
:25   if code is None or not code.is_redeemable or code.client_id != client.client_id:
:31   code.used = True
```

...and the commit happens later, in `token_service.py:52`. Under Postgres
READ COMMITTED, two concurrent POSTs with the same code both observe
`used = False` and both receive a token pair. `refresh_token_grant.py:27-30`
has the identical shape.

**Fix:** make the burn atomic —

```sql
UPDATE oauth_authorization_codes
   SET used = true
 WHERE code_hash = :hash AND used = false
RETURNING *
```

A zero-row result *is* the replay signal. `SELECT ... FOR UPDATE` is an
acceptable alternative.

**Also:** RFC 9700 §4.14.2 requires that a replayed refresh token revoke the
**entire token family**, so a thief who rotated first cannot keep using what
they obtained. Today `refresh_token_grant.py:28` returns a bare
`invalid_grant`. Add family revocation.

> Do this **before** phase 2. The burn logic moves into
> `exchange_authorization_code`, and you want it already correct when it moves.

### SEC-3 (MEDIUM-HIGH) — CSRF origin check is a prefix match

`api/auth.py:60`:

```python
any(origin.startswith(a) for a in allowed)
```

With `public_base = "https://mcp.example.com"`, an
`Origin: https://mcp.example.com.evil.test` passes, and the SEC-4 CSRF defence
on every cookie-authenticated mutation degrades to `SameSite=Lax` alone.

**Fix:** the correct idiom already exists in this repo, 30 lines away in
another file — `oauth/oidc/post_login_redirect.py:9`:

```python
next_url == a or next_url.startswith(a + "/")
```

For an `Origin` header, exact match is sufficient and correct; for `Referer`,
use the `== a or startswith(a + "/")` shape.

### SEC-8 (MEDIUM) — DCR rate limit uses the socket peer, not the client IP

`oauth/registration_controller.py:27` reads `request.client.host`. Behind the
reverse proxy that DEP-1 / `settings.trusted_proxies` assume, that is the
**proxy's** address for every request — so OAS-12's "10 registrations per hour
per IP" becomes a global 10/hour, and the first ten registrations lock out
everyone.

**Fix:** use the helper that already exists — `gateway/proxy.py:32`
`client_ip(request, settings)`.

### Tests

Add to `tests/test_upstream_oauth.py`: a discovery document whose
`authorization_servers[0]` points off-origin must be rejected without a token
request being issued. Add to `tests/test_oauth.py`: two concurrent redemptions
of one code yield exactly one token pair. Add to `tests/test_web_origins.py`:
`https://<public_base>.evil.test` is rejected as an Origin.

---

## Phase 2 — Adopt `mcp.server.auth`

**Effort:** 2–3 days · **Risk:** medium · **Depends on:** phases 0 and 1 ·
**This is the main event.**

### 2.1 New file: the provider

Create `packages/bundlemcp/bundlemcp/services/oauth_server/bundlemcp_oauth_provider.py`.

`BundlemcpOAuthProvider` implements `OAuthAuthorizationServerProvider`, is
constructed per-request from a `UnitOfWork` exactly as today's services are,
and holds the collaborators the current services hold.

**It belongs in `services/`** — verified: `mcp/server/auth/provider.py` imports
no Starlette. Run `uv run lint-imports` immediately after adding the import and
before writing any logic; if a future SDK release makes the provider module
import Starlette, the class must move to `oauth/` instead.

### 2.2 Deleted outright

| File / block | LOC | Replaced by |
|---|---|---|
| `services/oauth_server/token_service.py` | 66 | `TokenHandler` is the dispatcher |
| `services/oauth_server/token_grant.py` | 22 | `OAuthAuthorizationServerProvider` is the Protocol |
| `services/oauth_server/client_credentials.py` | 27 | `ClientAuthenticator` decodes Basic + post + none |
| `services/oauth_server/token_request.py` | 15 | `AuthorizationCodeRequest` / `RefreshTokenRequest` |
| `services/oauth_server/authorization_request.py` | 20 | SDK `AuthorizationRequest` (`handlers/authorize.py:25`) |
| `oauth/token_controller.py:27-68` body | ~42 | 3-line delegation to `TokenHandler.handle` |
| `oauth/authorize_controller.py:46-72` param handling | ~27 | `AuthorizationHandler.handle` |
| PKCE check, `authorization_code_grant.py:29-30` | 2 | `handlers/token.py:186-189` |
| `oauth/providers.py` wiring for the above | ~60 | one provider, one authenticator |

**≈ 280 LOC deleted**, of which ≈ 220 is protocol logic.

### 2.3 Rewritten, not deleted — bodies move into hooks

These files' *logic* survives; it relocates into provider hook bodies. Do not
treat this as a rewrite from scratch — port line by line.

| Today | Becomes |
|---|---|
| `authorization_service.py:111-128` `issue_code` | body of `authorize()` (after consent) |
| `authorization_code_grant.py:21-38` | `load_authorization_code()` + `exchange_authorization_code()` |
| `refresh_token_grant.py:21-36` | `load_refresh_token()` + `exchange_refresh_token()` |
| `token_issuer.py:21-43` `issue` | called from both `exchange_*` hooks; **keep the file** |
| `token_service.py:55-66` `revoke` | `revoke_token()` |
| `client_authenticator.py:15-25` | `HashedClientAuthenticator` (see 2.5) |

### 2.4 The five hooks that carry bundlemcp's own rules

**(a) `authorize(client, params) -> str`** — the richest hook. It must, in order:

1. Resolve the OAS-10 audience: `params.resource` → endpoint name via the
   reverse of the canonical resource identifier
   (`authorization_service.py:35-41` `_endpoint_name_from_resource`).
2. **Raise `AuthorizeError("invalid_target")` when `params.resource` is
   `None`.** The SDK types it `str | None`; **OAS-10 requires it.** This is the
   single most important behavioural guard to carry across — see
   `test_missing_resource_rejected` (`tests/test_oauth.py:415`).
3. Check `endpoint.enabled` and `endpoint.accepts(EndpointAuthMode.OAUTH)`
   (`authorization_service.py:70`) — else `invalid_target`.
4. If there is no `bmcp_session` cookie: return the `/login?next=...` URL built
   from `settings.public_base`, **never** the incoming `Host`
   (DEP-1; `authorize_controller.py:61-65`).
5. Check OAS-11 persistent consent (`authorization_service.py:91-99`). If
   granted, mint the code and return the client redirect. If not, park a
   `PendingAuthorization` in `SingleUseState` and return `/oauth/consent?...`.

Returning an arbitrary URL is the SDK's intended interactive seam — the same
pattern FastMCP uses at `fastmcp/server/auth/oauth_proxy/proxy.py:1109`.

**(b) `get_client(client_id)`** — map the `OAuthClient` row to
`OAuthClientInformationFull`.

**(c) `load_*` / `exchange_*`** — hashed lookups, the **atomic** single-use burn
from phase 1, refresh rotation, and propagation of `endpoint_id` into
`AccessToken.resource`.

**(d) `register_client(client_info)`** — hash the SDK-minted secret before
persisting; enforce the redirect-URI policy from
`client_registration_service.py:20-26`.

**(e) `revoke_token(token)`** — port `token_service.py:55-66` verbatim,
including "unknown tokens are ignored" (RFC 7009).

### 2.5 The client authenticator must be subclassed — and lives in `oauth/`

The SDK compares client secrets in **plaintext**:

```python
# mcp/server/auth/middleware/client_auth.py:113
if not hmac.compare_digest(client.client_secret.encode(), request_client_secret.encode()):
```

bundlemcp stores `client_secret_hash` (DOM-3) and compares with
`tokens_equal(hash_token(secret), client.client_secret_hash)`
(`client_authenticator.py:23`). Subclass and override `authenticate_request`.
In-tree precedent: `fastmcp/server/auth/auth.py:219`
`PrivateKeyJWTClientAuthenticator`.

> **Layering:** `ClientAuthenticator.authenticate_request(self, request)` takes
> a **Starlette `Request`** (`client_auth.py:39`). The subclass therefore
> **must live in `oauth/`, not `services/`** — putting it in `services/` breaks
> the framework-free contract and `uv run lint-imports` will fail.

Preserve the public-client rule: `token_endpoint_auth_method == "none"`
authenticates on `client_id` alone, because PKCE is the proof
(`client_authenticator.py:19-20`).

### 2.6 Controllers become thin delegations

`oauth/token_controller.py` keeps its `Controller` shape, its prefix, and its
RATE-5 auth-failure guard; the body collapses:

```python
@route.post("/token")
async def token(self, request: Request, handler: TokenHandlerProvider,
                auth_failures: AuthFailureGuardProvider) -> Response:
    response = await handler.handle(request)
    if response.status_code in (400, 401):
        # RATE-5: a failed grant is a credential-scan signal
        result = await auth_failures.record(request)
        if not result.allowed:
            locked = oauth_error_response("too_many_requests", "...", status=429)
            locked.headers["Retry-After"] = str(result.retry_after)
            return locked
    return response
```

Note the guard now keys off the **response status** rather than the
`CREDENTIAL_ERRORS` set (`token_controller.py:19`), because the SDK raises no
`OAuthError`. Confirm the SDK returns 401 for `invalid_client` and 400 for
`invalid_grant` before deleting the frozenset.

`introspect` (`:70-92`) and `revoke` — decide per 2.7 — are otherwise untouched.

### 2.7 Three behaviour changes to decide deliberately

| # | Change | Recommendation |
|---|---|---|
| 1 | `RegistrationHandler` defaults a missing `token_endpoint_auth_method` to `client_secret_post` (`handlers/register.py:51`), contradicting **OAS-2**'s public-client default | **Keep `RegistrationController` + `ClientRegistrationService` in phase 2.** Revisit later. `tests/test_oauth.py:86-95` asserts `"client_secret" not in body` for exactly this request and would break. |
| 2 | `RegistrationHandler` mints `client_id = str(uuid4())`, losing the `bmcp_client_` prefix | Follows from (1) — no change if you keep your own controller. |
| 3 | `RevocationHandler` **requires client authentication** (`handlers/revoke.py:38`); bundlemcp's `/oauth/revoke` takes none (`token_controller.py:94-99`) | **Adopt the SDK's behaviour** — RFC 7009 §2.1 requires it for confidential clients and the current endpoint is unauthenticated *and* unrate-limited. But it **is** a contract change: announce it, and update `test_revocation` (`:348`), which posts only `token`. |

### 2.8 Tests

**Must change:**

| Test | Why |
|---|---|
| `test_oauth.py:120-133` `_exchange` | SDK error bodies are `TokenErrorResponse` — different shape |
| `test_oauth.py:348` `test_revocation` | now needs `client_id` + client auth (2.7 #3) |
| `test_oauth.py:415` `test_missing_resource_rejected` | assert the new `invalid_target` redirect rather than the current message |
| `test_oauth.py:86-95` `_register_client` | only if 2.7 #1 is reversed |

**Must NOT be weakened — this is the regression net:**

- `test_full_pkce_flow_and_mcp_call` (`:147`) — OAS-9 end to end
- `test_token_bound_to_endpoint_audience` (`:187`) — **ADR-0009, the core invariant**
- `test_consent_skipped_on_second_authorize` (`:173`) — OAS-11
- `test_code_single_use_and_pkce_verified` (`:204`)
- `test_refresh_rotation_revokes_old` (`:252`) — OAS-4
- `test_authorize_login_next_uses_public_url_behind_proxy` (`:386`) — DEP-1

If any of these needs editing to pass, **stop** — behaviour has changed.

### 2.9 What could break

- **Import-linter.** Verify `services/` may import `mcp.server.auth.provider`
  *before* writing logic. The `HashedClientAuthenticator` must be in `oauth/`.
- **`AuthorizationParams.redirect_uri_provided_explicitly`** has no bundlemcp
  analogue. Get its semantics right or you loosen redirect-URI matching — RFC
  6749 §3.1.2.1 distinguishes an omitted `redirect_uri` (use the single
  registered one) from a supplied one (must match exactly).
- **`httpx2`.** `mcp.client.auth` uses `httpx2`; `mcp.server.auth` does not.
  Confirm no `httpx2` leaks into the gateway image.
- **Metadata drift.** The metadata document is now maintained by hand while the
  handlers are the library's. Add an assertion that every endpoint advertised in
  `authorization_server_metadata.py` is a route that actually exists.

---

## Phase 3 — OAS-14 (RFC 9207 `iss`) and the redirect-building bug

**Effort:** ~2 hours · **Risk:** low · **Depends on:** phase 2 (touches the same
lines) · Do it while the redirect code is already open.

### The bug (SEC-6, MEDIUM — correctness becoming security)

`oauth/authorize_controller.py:44`:

```python
RedirectResponse(f"{pending.redirect_uri}?{urlencode(params)}", status_code=302)
```

...and identically at `oauth/oauth_error_response.py:33`.

A registered `https://app.example/cb?tenant=x` becomes
`https://app.example/cb?tenant=x?code=…`. The client parses `tenant` as
`x?code=…` and **never sees `code`**. RFC 6749 §3.1.2 explicitly permits a
query component in a registered redirect URI.

### The fix, which closes OAS-14 in the same call

`fastmcp/server/auth/redirect_validation.py:68` `build_client_redirect(url, params, *, iss)`
merges query parameters correctly **and** adds the RFC 9207 `iss` parameter.
FastMCP is already a dependency.

1. Replace both f-string concatenations with `build_client_redirect(...)`,
   passing `iss=settings.public_base`.
2. Add `authorization_response_iss_parameter_supported: true` to
   `schemas/oauth/authorization_server_metadata.py`.
3. Apply it to **error** redirects too — OAS-14 requires `iss` on every
   authorization response, success and failure alike.

### Tests

`tests/test_oauth.py`: a client registered with a query-bearing redirect URI
receives a parseable `code`; every authorization redirect carries `iss`; an
error redirect carries `iss`.

---

## Phase 4 — OAS-13 (Client ID Metadata Documents) via FastMCP

**Effort:** ~1 day · **Risk:** low (new feature, nothing to regress) ·
**Depends on:** phase 2

OAS-13 is specced and unimplemented — `grep` for
`client_id_metadata_document` across `oauth/`, `services/oauth_server/` and
`schemas/` returns nothing.

`fastmcp/server/auth/cimd.py:198` `CIMDFetcher` already implements document
fetch, `client_id`-echo validation, `redirect_uris` matching, SSRF protection
and `Cache-Control`-aware caching — roughly **450 lines you would otherwise
write**, in a package already installed. `PrivateKeyJWTClientAuthenticator`
(`fastmcp/server/auth/auth.py:219`) handles the asymmetric client
authentication CIMD clients use.

### What must still be bundlemcp's

1. **Cache in Valkey, not in `CIMDFetcher`'s process-local `_CIMDCacheEntry`.**
   [ADR-0004](adr/0004-postgres-redis-state-split.md) and spec 30 forbid
   replica-local state a request depends on. Wrap the fetcher; do not use its
   cache.
2. **Route CIMD fetches through the phase-1 egress policy.** FastMCP has its own
   SSRF allowlist; two gates disagreeing is worse than one. Decide which is
   authoritative and document it.
3. Advertise `client_id_metadata_document_supported: true` in
   `schemas/oauth/authorization_server_metadata.py`.

---

## Not doing — evaluated and rejected

**Replacing `oauth/upstream_client/httpx_upstream_provider.py` (118 LOC) with
`authlib.integrations.httpx_client.AsyncOAuth2Client`.** It *is* async, and it
*is* what FastMCP's OAuthProxy uses. But it saves ~60 lines of straightforward
`httpx` calls, reintroduces a hard direct dependency on the library phase 0
just removed, and leaves the surrounding ~500 lines (encrypted per-`(server,
user)` rows, Valkey single-flight refresh) untouched either way. Revisit only
if upstream token handling starts failing on protocol edge cases.

**`mcp.client.auth.OAuthClientProvider` for upstream tokens.** Its flow blocks
on `redirect_handler` + `callback_handler` (`mcp/client/auth/oauth2.py:416-419`)
— FastMCP's defaults open a browser and run a localhost callback server. UPO-3
requires the opposite: fail the tool call *now* with a structured "connect at …"
error. And its `TokenStorage` keys on `server_url` with no user dimension.

---

## Architecture and documentation notes

### ADRs to write (append-only; land in the same PR as the code)

**`docs/adr/0031-mcp-sdk-auth-framework.md`** — *"MCP SDK auth framework for the
OAuth server; joserfc for JOSE"*

- **Context:** ADR-0014 chose Authlib as the OIDC relying-party library and
  hand-written services for the AS role; ADR-0028 factored those services.
  Since then: `authlib.jose` was deprecated with removal at 2.0, and MCP SDK
  v2 shipped an async `OAuthAuthorizationServerProvider` with first-class
  RFC 8707 `resource` support.
- **Decision:** adopt `mcp.server.auth` handler classes + provider Protocol for
  request parsing, grant dispatch and PKCE; keep introspection, metadata,
  consent, token issuance and per-endpoint audience binding hand-written;
  replace `authlib.jose` with `joserfc`; drop `authlib` as a direct dependency.
- **Reasons:** Authlib's AS framework is sync and Flask/Django-only (evidence
  in §0 above); the SDK's provider is async, Pydantic-native, MCP-spec-aware,
  already installed, and its auth surface survived the v1→v2 major bump.
- **Consequences:** (+) ~220 LOC of security-critical protocol code deleted at
  zero dependency cost; (+) PKCE S256-only and redirect re-matching are now
  library-enforced. (−) bundlemcp tracks MCP SDK releases on the AS surface;
  (−) `RevocationHandler` requires client auth, a contract change; (−) the
  metadata document is hand-maintained while the handlers are the library's,
  so they can drift.
- **Supersedes:** ADR-0014's authlib clause. **Extends:** ADR-0028.

**`docs/adr/0032-upstream-egress-policy-scope.md`** — *"The egress policy
governs every outbound URL, not just MCP transport"*

- **Context:** `check_url_allowed` existed but was applied at exactly one call
  site; upstream OAuth discovery followed a remote-supplied
  `authorization_servers[0]` and POSTed the gateway's client secret to it.
- **Decision:** every outbound HTTP request originating from a
  remote-influenced URL passes the egress policy; upstream OAuth binds and
  verifies the discovered issuer (UPO-8).
- **Consequences:** one authoritative SSRF gate — including for the
  phase-4 CIMD fetcher, which must not use FastMCP's separate allowlist.

Add both to the index table in `docs/adr/README.md`, and mark ADR-0014 as
partially superseded there.

### Spec updates

**`spec/20-oauth-server.md`** — add a note distinguishing library-driven from
bundlemcp-owned requirements. Keep every requirement ID stable:

| Now library-driven | Still bundlemcp's |
|---|---|
| OAS-1 (metadata *shape*), OAS-2 (DCR mechanics), OAS-3 (code + PKCE), OAS-4 (grant mechanics), OAS-6 | OAS-5 (introspection), OAS-7 (direct-DB validation), OAS-10 (endpoint audience **binding**), OAS-11 (persistent consent), OAS-12 (DCR rate limit), OAS-14 (`iss`) |

Mark **OAS-13** and **OAS-14** as implemented when phases 3 and 4 land.

**`spec/23-upstream-oauth.md`** — mark **UPO-8** implemented after phase 1.

**`spec/70-security.md`** — record that SEC-1's egress requirement now covers
the upstream-OAuth discovery chain, and reference ADR-0032.

### arc42

- `docs/arc42/08-crosscutting-concepts.md` — update the authentication section:
  the AS surface is now library handlers over a bundlemcp provider.
- `docs/arc42/11-risks-and-technical-debt.md` — **remove** the Authlib
  deprecation risk once phase 0 ships; **add** "AS surface tracks MCP SDK
  releases" and "metadata document maintained separately from the handlers that
  serve it".

### LikeC4

`docs/likec4/model.c4` — if the OAuth server appears as a distinct element,
relabel it to show the SDK handler boundary. Re-run
`npx likec4 validate docs/likec4` (CI job `diagrams` enforces this).

### CLAUDE.md conventions that apply

- **Module naming:** `authlib_oidc_provider.py` → `jose_oidc_provider.py`. A
  module is named for what it holds.
- **No dataclasses:** the SDK's handlers are `@dataclass`, but that is *library*
  code. Every new bundlemcp model stays a `BaseModel`. Do not mirror the
  library's style inward.
- **Field descriptions:** every field on any new DTO carries a `description`;
  on `schemas/` it is published API surface.
- **Docstrings never cite requirement IDs.** `OAS-10` belongs in an inline `#`
  comment, a test name, or an error message — never a docstring.
- **Controllers, not route functions.** The delegation methods stay on
  `Controller` subclasses.

---

## Execution checklist

| # | Phase | Ship alone? | Gate |
|---|---|---|---|
| 1 | Phase 0 — joserfc + claims registry | ✅ | 4 new OIDC tests; `pytest -q`, `ruff check .`, `lint-imports` green |
| 2 | Phase 1 — SEC-2 (egress + UPO-8) | ✅ | off-origin `authorization_servers[0]` rejected before any token request |
| 3 | Phase 1 — SEC-5 (atomic burn + family revocation) | ✅ | concurrent-redemption test |
| 4 | Phase 1 — SEC-3, SEC-8 | ✅ | origin-suffix test; DCR limit keys on `client_ip()` |
| 5 | Phase 2 — provider + handlers | ⚠️ one PR | the six regression tests unchanged and green |
| 6 | Phase 3 — `iss` + redirect building | ✅ | query-bearing redirect URI test |
| 7 | Phase 4 — CIMD | ✅ | Valkey-cached, egress-gated |

Every phase must leave `uv run pytest -q`, `uv run ruff check .` and
`uv run lint-imports` green — `lint-imports` especially in phase 2, where the
layering question is live.
