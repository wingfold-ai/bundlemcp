# ADR-0017: Upstream OAuth client + token encryption at rest

**Status:** accepted · **Date:** 2026-07-03

## Context

Some upstream MCP servers are OAuth-protected (spec 23). The schema had the
tables (`UpstreamOAuthClient`, `UpstreamOAuthToken` with `*_encrypted`
columns), the `ServerAuthMode.UPSTREAM_OAUTH` enum, and
`settings.token_encryption_keys` — but no client-flow code and **no encryption
code**, so protected upstreams didn't work and the "encrypted" columns would
have stored plaintext (DOM-3/DEP-9 unmet). This ADR records the design that
filled the gap.

## Decision drivers

- Proactive-expiry refresh is reliable and hermetically testable; parsing 401s
  out of FastMCP is not, so it's only the secondary (reactive) path.
- MultiFernet gives zero-downtime key rotation for free.
- Reusing the injectable-provider pattern kept the whole flow testable without a
  real IdP (ARC-14).

## Decision

- **Encryption (DOM-3/DEP-9):** `crypto.py` `TokenCipher` wraps Fernet via
  **MultiFernet** — the first configured key encrypts, all decrypt, so keys
  rotate without a migration; `rotate()` re-encrypts lazily on write. No keys +
  an upstream-oauth server = a clear startup/call error, never plaintext.
- **Client model:** an injectable `UpstreamOAuthProvider` protocol (mirroring
  the OIDC RP `OidcProvider`) with a real `HttpxUpstreamProvider`; tests inject
  a fake. **Scope:** endpoint discovery (RFC 9728 → 8414 chain) +
  **pre-registered** client credentials. Dynamic registration against the
  upstream is opportunistic only (if metadata advertises it); pre-registered is
  the supported path.
- **Storage (UPO-2/5):** `UpstreamTokenStore` keeps the encrypted token bundle
  keyed `(server_id, user_id)`, `NULL` = shared. `status()` exposes connection
  state + account hint only — never token values.
- **Refresh (UPO-4):** **proactive-by-expiry** (refresh within a 60 s skew
  before the stored `expires_at`) under a **Redis single-flight lock** per
  token row; a refresh failure invalidates the row and raises `NeedsConnect`.
  The JSON call path additionally **force-refreshes and retries once** on an
  upstream error (the 401-despite-fresh-token case), reusing the same metering
  idempotency key (MID-3: internal retry doesn't re-fire pre-call).
- **Connect (UPO-3):** a browser flow (`oauth/upstream_connect.py`) — admin for
  the shared connection, `?as=me` for per_user — with PKCE + single-use Redis
  state, mirroring the OIDC login. The **per-user connect prompt is a
  structured MCP error carrying the connect URL** (reliable across clients);
  MCP-elicitation-based connect is deferred (the relay already supports it, so
  it can be added without rework).
- **Isolation (UPO-6):** a `none`-auth endpoint cannot expose a bundle
  containing a `per_user` upstream server — enforced at endpoint upsert
  (`api/validators.py`), with helpers ready for membership and identity-mode
  changes.

## Alternatives considered

_Not recorded at the time of the decision._

## Consequences

### Positive

- OAuth-protected upstreams work, per-(server,user) or shared; tokens are
  genuinely encrypted at rest with a rotation story (DEP-9 met).
- The single-flight lock prevents refresh stampedes (proven: three
  concurrent callers → one refresh).

### Trade-offs

- The reactive 401-retry is implemented for the JSON path only; the
  progress/SSE path relies on proactive-expiry refresh (a mid-stream 401 is
  rare and the token was refreshed before the call). Documented, not hidden.
- Dynamic client registration against upstreams is not the primary path;
  providers without discovery/DCR require an admin to enter pre-registered
  credentials.

