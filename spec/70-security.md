# 70 — Security model

**Status:** Accepted · **Origin:** new

## Summary

The threat model and the cross-cutting security controls: SSRF egress policy,
CORS/CSRF, size limits, registration abuse, and secret handling. Individual
specs reference these controls instead of re-deriving them.

## Trust model

| Actor | Trust |
|---|---|
| Admin (OIDC, `is_admin`) | Trusted to configure; NOT trusted to reach arbitrary internal networks through the gateway (SSRF controls still apply) |
| Endpoint caller (OAuth user / API key) | Untrusted; sees only what the endpoint exposes |
| Anonymous (`none`-auth endpoints) | Untrusted; explicitly opted in per endpoint |
| Upstream MCP server | Semi-trusted: receives forwarded identity/headers, but its responses/notifications are validated like external input |
| External OIDC IdP | Trusted for authentication claims |
| Application layer (metering hook, service keys) | Trusted service-to-service |

## Requirements

### Egress / SSRF

- **SEC-1** All gateway-initiated HTTP to admin-supplied URLs (server probes
  [SRV-2](10-server-registry.md), live tool calls, upstream OAuth discovery
  [UPO-1](23-upstream-oauth.md), inspector ad-hoc targets
  [INS-1](53-inspector.md)) goes through one egress policy layer.
- **SEC-2** Default egress policy: **block link-local/metadata ranges**
  (`169.254.0.0/16`, IPv6 equivalents — cloud metadata endpoints) and the
  gateway's own loopback; **allow private RFC 1918 ranges** (compose-network
  upstreams are the primary use case). Operators can tighten
  (`BUNDLEMCP_EGRESS_DENY_CIDRS`) or extend (`…_ALLOW_CIDRS`, evaluated
  first). Policy is enforced on the **resolved IP at connect time** (not just
  the hostname) to defeat DNS rebinding, including on redirects.
- **SEC-3** Egress denials are logged (WARN) and surfaced as clear errors in
  the UI/API; they are not silent failures.

### Browser security (CORS / CSRF / cookies)

- **SEC-4** Management API (`/api/v1`): CORS allowlist is exactly the web
  app's origin(s) (`BUNDLEMCP_WEB_ORIGINS`); credentials allowed only for
  those. State-changing requests authenticated by the admin session cookie
  MUST be CSRF-protected: `SameSite=Lax` cookies **plus** Origin/Referer
  check (double-submit token as fallback for non-browser callers is not
  needed — those use API keys).
- **SEC-5** MCP endpoints (`/{endpoint}/mcp`): permissive CORS
  (`Access-Control-Allow-Origin` reflecting the request origin, no
  credentials — auth is header-based) so browser-based MCP clients work;
  `Mcp-Session-Id` and `WWW-Authenticate` exposed via
  `Access-Control-Expose-Headers`.
- **SEC-6** OAuth browser pages (authorize, consent, upstream connect) carry
  standard hardening headers (CSP, `X-Frame-Options: DENY` /
  `frame-ancestors 'none'` against clickjacked consent).

### Abuse resistance & limits

- **SEC-7** Request body size limits: `/{endpoint}/mcp` and `/api/v1` default
  1 MiB (runtime-configurable); upstream **response** size cap (default
  16 MiB) so one tool result can't exhaust replica memory. Violations →
  413 / structured MCP error.
- **SEC-8** Dynamic client registration ([OAS-2](20-oauth-server.md)) is
  rate-limited per IP (Redis, shares [RATE-5](16-rate-limiting.md)
  machinery) and capped by a global unapproved-client quota; stale
  never-used registrations are purged with the OAS-8 job.
- **SEC-9** Auth-failure rate limiting per [RATE-5](16-rate-limiting.md);
  lockout events are visible in metrics ([OBS-2](51-observability.md)).

### Secrets

- **SEC-10** Restating as testable requirements: secret values (API keys,
  tokens, static/forwarded header values, client secrets) never appear in
  logs, metrics labels, audit records, API responses (beyond one-time
  display at creation), or error messages. A unit-test helper asserts
  redaction on representative paths.
- **SEC-11** `?include_secrets=true` export ([EXP-2](42-export-import.md)):
  admin-session-only (not service keys), always audit-logged, response
  carries an explicit warning field; docs tell operators to treat the file
  as a credential.

## Out of scope

- Network-level controls (firewalls, service mesh) — deployment guidance in
  [71-deployment.md](71-deployment.md).
- Pen-testing/audit process.

## Open questions

- None.
