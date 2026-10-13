# Proposal: complete the OAuth server

## Why

The OAuth 2.1 server toward MCP clients works end to end, but five parts of the original specification were never
built: introspection accepts only a service key, the token endpoint ignores `resource`, users cannot see or revoke
their own consents, a refused bearer gets the generic challenge instead of `error="invalid_token"`, and the end-to-end
test stops at `tools/list`. The main specs were narrowed to what exists; this change restores the rest, or records
where the maintainers should amend the requirement instead.

## What Changes

- **Introspection by client credentials (AUTH-5).** Besides a service-kind API key, a caller may authenticate to
  `POST /oauth/introspect` with the client credentials of a confidential client an admin has authorised for
  introspection. See the open decision below.
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

## Open decision

The maintainers decide these before the change is applied.

- **AUTH-5: build or amend.** Dynamic client registration is open to anyone, so "any registered client may introspect"
  would undo the protection against anonymous fishing; the delta therefore restricts it to clients an admin has
  authorised, which needs a new per-client flag and a management route. [UPS-31](../../specs/upstreams/spec.md)
  already tells resource servers to use a service key. **Recommendation: amend** — drop the AUTH-5 delta, keep the
  current "service key only" text, and remove group 2 from `tasks.md`.
- **AUTH-10: the default for a missing `resource`.** The original text said a request without `resource` defaults to
  "the endpoint whose protected-resource metadata initiated the flow". The authorization server cannot observe which
  metadata document a client read, and `test_missing_resource_rejected` already asserts that authorize refuses a
  missing `resource`. The delta keeps authorize strict and defines the token-endpoint default as the grant's own
  audience. **Recommendation: accept the delta as written**, which amends the original default.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `auth`: AUTH-5 (introspection by client credentials), AUTH-9 (`tools/call` in the integration test), AUTH-10
  (`resource` at the token endpoint), AUTH-11 (users revoke their own consents).
- `endpoints`: EP-3a (a refused bearer gets `error="invalid_token"`).

## Impact

- **Code:** `api/oauth/introspection_auth.py`, the token request DTO and grants in `application/oauth_server/`,
  `api/mcp/routing/authentication/` (challenge selection), `api/management/controllers/me_controller.py`,
  `application/management/user_service.py` (or a new self-service consent service), `apps/web` (a "my connections"
  view for non-admin users).
- **APIs:** two new `/api/v1/me/consents` routes (OpenAPI and generated TS types regenerate); a new form field on
  `/oauth/token`; a changed `WWW-Authenticate` value on refused bearers. If AUTH-5 is built: a per-client introspection
  flag (migration) and a management route to set it.
- **Tests:** `packages/bundlemcp/tests/api/test_oauth.py`, `tests/integration/test_oauth_flow.py`.
- **Docs:** `docs/guide/authentication.md`, `docs/manage/users.md`, `docs/integrate/http-surface.md`,
  `docs/integrate/upstream-identity.md` (introspection callers).
- **ADR:** none; ADR-0009 (endpoint-bound tokens and consent) already covers the design.
- **Dependencies:** none on other open changes.
