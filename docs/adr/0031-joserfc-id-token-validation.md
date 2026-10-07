# ADR-0031: joserfc verifies ID tokens; issuer and audience are validated explicitly

**Status:** accepted · **Date:** 2026-09-06 · **Amends:** [ADR-0014](0014-gateway-rendered-oauth-authlib.md)

## Context

ADR-0014 chose Authlib as the OIDC relying-party library. bundlemcp's entire use of it was one call pair,
`authlib.jose.jwt.decode` + `claims.validate()`, in the provider that turns an IdP's ID token into `OidcClaims`. Two
things changed since:

- `authlib.jose` is deprecated and scheduled for removal in Authlib 2.0; the maintainers point at `joserfc`, which
  Authlib itself now depends on. joserfc is therefore already in the lockfile (also via FastMCP's server extra).
- `claims.validate()` was called without `claims_options`, and Authlib skips the `iss` and `aud` checks when no option
  names them. Only the signature and the time claims were verified, while the `iss` read from the token keyed the local
  user identity. On a shared IdP realm a token minted for a different client of the same realm passed.

## Decision drivers

- The deprecation would have become an `ImportError` at the next Authlib major; the replacement is the library Authlib
  delegates to.
- joserfc validates nothing implicitly, which makes the claim checks visible in the code that owns them instead of
  hidden behind an option dictionary.
- Zero installed-package delta.

## Decision

- `JoseOidcProvider` (renamed from `AuthlibOidcProvider`) decodes the ID token with `joserfc.jwt.decode` against the
  issuer's JWKS and then validates the claims through a `JWTClaimsRegistry` that requires `iss` to equal the discovery
  document's `issuer`, `aud` to equal the configured client id, and `exp` and `sub` to be present. Every failure
  surfaces as one `OidcError`.
- The provider's HTTP errors (`httpx.HTTPError`, a malformed body) become `OidcError` too, so the login callback answers
  400 instead of 500, and the callback refuses an `error` parameter before attempting an exchange.
- The discovery, token and JWKS URLs pass the egress policy (SEC-1). An issuer on loopback needs an explicit egress
  allow entry.
- The provider takes an `httpx.AsyncClient` factory, so the JOSE path is tested with a mock transport and a per-test
  key. The `OidcProvider` Protocol is unchanged.
- `authlib` is no longer a direct dependency; `joserfc>=1.7` is.

## Alternatives considered

_Not recorded at the time of the decision._

## Consequences

### Positive

- OIDC Core 3.1.3.7 steps 2 and 3 are enforced and covered by tests that fail against the previous code.
- The relying-party path is exercised hermetically for the first time.

### Trade-offs

- An IdP whose `aud` is a list containing the client id relies on joserfc's list handling of `value`; confirm against a
  new realm before shipping it.

