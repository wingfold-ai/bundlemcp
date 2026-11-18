# Spec Delta

## MODIFIED Requirements

### Requirement: SEC-6 OAuth browser page hardening
OAuth browser pages (authorize, consent, upstream connect) MUST carry standard hardening headers: a CSP of
`default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; form-action 'self'`, `X-Frame-Options: DENY`
against clickjacked consent, and `Cache-Control: no-store`. `form-action` is widened on one page only, the consent
page, and only by the redirect URI of the authorization it decides, already validated against the client's
registration ([AUTH-2](../auth/spec.md), [AUTH-13](../auth/spec.md)): browsers apply `form-action` to
the redirect that answers a form post, so without it Approve and Deny could never reach a client on another origin.
The source expression is that URI's scheme, host, port and path, never a wildcard, a bare scheme or another client's
URI; because CSP disregards the path of a redirected request, what it admits in practice is that redirect URI's origin.
A redirect URI that cannot be written as a source expression leaves `form-action 'self'` in place, and the consent
answer is a same-origin page linking to the client instead of a redirect.

While an operator asset directory is configured ([AUTH-39](../auth/spec.md)), every page's CSP also admits
stylesheets, fonts and images from the gateway's own origin, and nothing else:
`default-src 'none'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self'; frame-ancestors 'none'`,
followed by the same `form-action` as without it. Scripts, frames, connections and every other origin stay refused.
Without an asset directory the CSP is exactly the one above.

#### Scenario: Consent page names exactly this client's redirect URI
- **WHEN** the consent page renders for an authorization with redirect URI `https://claude.ai/api/mcp/auth_callback?x=1`
- **THEN** its CSP `form-action` is `'self' https://claude.ai/api/mcp/auth_callback` and it carries
  `X-Frame-Options: DENY` and `Cache-Control: no-store`

#### Scenario: Unwritable redirect URI keeps form-action self
- **WHEN** the redirect URI cannot be written as a CSP source expression
- **THEN** `form-action` stays `'self'` and the consent answer is a same-origin page linking to the client

#### Scenario: Browser reaches a cross-origin client
- **WHEN** a user approves consent in Chromium for a client whose redirect URI is on another origin
- **THEN** the browser follows the redirect to that client

#### Scenario: Assets configured admit same-origin styles, fonts and images
- **GIVEN** an operator asset directory is configured
- **WHEN** the consent page renders for redirect URI `https://claude.ai/api/mcp/auth_callback`
- **THEN** its CSP is `default-src 'none'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self';
  frame-ancestors 'none'; form-action 'self' https://claude.ai/api/mcp/auth_callback`

#### Scenario: No asset directory keeps the policy
- **WHEN** no asset directory is configured
- **THEN** every page's CSP is the one without `'self'` in `style-src` and without `font-src` or `img-src`
