# Tasks

## 1. Domain rule

- [ ] 1.1 Add `OriginPolicy` in `domain/endpoints/origin_policy.py` (normalise an entry, `allows(origin,
  public_origin)`, `default_for(auth_modes)`) and `allowed_origins` on `Endpoint`. Verify with domain tests citing EP-24
  for normalisation, every invalid form, `*` alone, the public origin, `null`, and both defaults.

## 2. Persistence and API

- [ ] 2.1 Add the column to the endpoint row and repository mapping, and Alembic revision `0011` (add, backfill from
  `auth_modes`, downgrade drops it). Verify with a hermetic migration test citing EP-24 (an `oauth` row gets `["*"]`,
  a `none` row `[]`) and the sqlite repository tests.
- [ ] 2.2 Add the field to `EndpointUpsert` (optional, validated through `OriginPolicy`) and `EndpointRead`, and resolve
  the default in `EndpointService.upsert`. Verify with API tests citing EP-24: an omitted field gets the default for
  each auth mode, a listed one round-trips normalised, and each invalid form answers `422` naming the entry; and with a
  bootstrap test that a document's endpoint accepts the field.
- [ ] 2.3 Run `cd apps/web && npm run openapi` and verify the generated files list the field.

## 3. MCP edge

- [ ] 3.1 Check `Origin` in `AdmissionGate.admit_caller` after the endpoint lookup and before authentication, carry the
      granted origin on `EndpointContext` and on a post-lookup `RequestRejected`, and apply the CORS headers at
      `McpGatewayRouter`'s exit for POST, GET and DELETE. Verify with ASGI tests citing EP-24 and SEC-5: a listed origin
      is served with CORS (JSON and SSE), another origin gets `403` with no grant and the credential is never checked,
      no `Origin` is unaffected, the gateway's own origin is always allowed, and a 401 challenge to a listed origin is
      readable.
- [ ] 3.2 Add `OPTIONS /{endpoint_name}/mcp` (`McpGatewayRouter.preflight`) and remove the MCP branch from
  `PathScopedCors`. Verify with ASGI tests citing SEC-5 that an allowed preflight is answered with the methods, headers
  and max age, a disallowed one gets `403` without `Access-Control-Allow-*`, and `/api/v1` keeps the allow-list.
- [ ] 3.3 Update `tests/api/test_mcp_cors.py` from `harden-http-edge` to the per-endpoint rule and verify the whole
  suite passes with `uv run pytest -q`.

## 4. Admin UI

- [ ] 4.1 Add an "Allowed browser origins" input (one origin per line, `*` for any) with help text saying it is not
  authentication to `apps/web/app/pages/endpoints/[name].vue`, sending `allowed_origins` on save. Verify with
  `npm run typecheck` and an e2e scenario in `apps/web/tests/endpoint-config.spec.ts` that an edited list persists
  across a reload (with its `spec-map.json` entry and `npm run test:map`).

## 5. Documentation and ADR

- [ ] 5.1 Add `docs/adr/0049-browser-origins-are-an-endpoint-setting.md` and its index entries. Verify
  `python3 tools/check_adr_graph.py`.
- [ ] 5.2 Document the field in `docs/manage/endpoints.md`, the CORS and `403` behaviour in
  `docs/integrate/http-surface.md` and `docs/integrate/errors.md`, the bootstrap example in
  `docs/self-hosting/bootstrap.md`, and the upgrade note (open endpoints refuse other origins) in
  `docs/self-hosting/deploy.md`. Verify `python3 tools/check_docs_links.py` and `check_docs_symbols.py`.

## 6. Gates

- [ ] 6.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`, the four
  `tools/check_*.py` scripts, `python3 tools/check_spec_ids.py`, `cd apps/web && npm run openapi` (no diff), and
  `openspec validate --all --strict`; then the integration suite and `npx playwright test` against the rebuilt stack.
