# Proposal: complete the OAuth server

## Why

The OAuth 2.1 server toward MCP clients works end to end, but five parts of the original specification were never
built: the token endpoint ignores `resource`, users cannot see or revoke their own consents, a refused bearer gets the
generic challenge instead of `error="invalid_token"`, and the end-to-end test stops at `tools/list`. A fifth, client
credentials at introspection, is not built: introspection stays service-key only (see the decisions).

## What Changes

- **`resource` at the token endpoint (AUTH-10).** `POST /oauth/token` accepts an RFC 8707 `resource` parameter; when
  present it must name the audience of the code or refresh token being redeemed, otherwise the request is refused
  with `invalid_target`. Without it, the issued token inherits the grant's audience, which is the endpoint the
  authorize request named.
- **Self-service consents (AUTH-11).** A signed-in user lists and revokes their own consents through
  `GET /api/v1/me/consents` and `DELETE /api/v1/me/consents/{consent_id}`, and in the web app. Revocation still
  revokes the tokens issued under the consent. Admins keep their existing routes.
- **`invalid_token` challenge (EP-3a).** A bearer that is expired, revoked, unknown or bound to another endpoint is
  answered 401 with `WWW-Authenticate: Bearer error="invalid_token", resource_metadata="…"`. A request that carries
  no credentials keeps the plain challenge (RFC 6750 §3.1).
- **`tools/call` in the integration test (AUTH-9).** The compose-stack happy path also calls a tool with the access
  token.

## Decisions

Settled by the maintainers on 2026-10-15:

- **AUTH-5: amend — introspection stays service-key only.** Dynamic client registration is open to anyone, so letting
  registered clients introspect would need an admin-granted per-client flag and a management route to undo the
  protection against anonymous fishing, and [UPS-31](../../specs/upstreams/spec.md) already tells resource servers to
  use a service key. The main spec's current AUTH-5 text stands; this change does not modify it.
- **AUTH-10: the token endpoint defaults to the grant's own audience.** The original default, "the endpoint whose
  protected-resource metadata initiated the flow", is not observable by the authorization server, and authorize
  already refuses a missing `resource`. The delta keeps authorize strict and amends the token-endpoint default.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `auth`: AUTH-9 (`tools/call` in the integration test), AUTH-10 (`resource` at the token endpoint), AUTH-11 (users
  revoke their own consents).
- `endpoints`: EP-3a (a refused bearer gets `error="invalid_token"`).

## Impact

- **Code:** the token request DTO and grants in `application/oauth_server/`,
  `api/mcp/routing/authentication/` (challenge selection), `api/management/controllers/me_controller.py`,
  `application/management/user_service.py` (or a new self-service consent service), `apps/web` (a "my connections"
  view for non-admin users).
- **APIs:** two new `/api/v1/me/consents` routes (OpenAPI and generated TS types regenerate); a new form field on
  `/oauth/token`; a changed `WWW-Authenticate` value on refused bearers.
- **Tests:** `packages/bundlemcp/tests/api/test_oauth.py`, `tests/integration/test_oauth_flow.py`.
- **Docs:** `docs/guide/authentication.md`, `docs/manage/users.md`, `docs/integrate/http-surface.md`.
- **ADR:** none; ADR-0009 (endpoint-bound tokens and consent) already covers the design.
- **Dependencies:** none on other open changes.
