# Tasks

## 1. Decide before applying

- [x] 1.1 Settle the UI-2 open decision in `proposal.md` (no-access page or keep the redirect); if amending, delete the
  UI-2 block from `specs/admin-ui/spec.md` and verify `openspec validate complete-admin-ui --strict` still passes

## 2. Upstream naming in every copy (UI-7)

- [x] 2.1 Retitle `apps/web/app/pages/upstreams/[name].vue` to *Upstream server: {name}* and replace the bare *server*
  copy in `upstreams/index.vue` (protocol tooltip), `upstreams/[name].vue` (name error, per-user OAuth hint) and
  `components/ServerRegistration.vue` (name error); verify with `grep -rn "[Ss]erver" apps/web/app` that what remains is
  *Upstream server(s)* or code identifiers
- [x] 2.2 Update the Playwright assertions and `apps/web/tests/spec-map.ts` for the new copy and add a UI-7 test for the
  detail title and error copy; verify `npm run test:ui` passes against the demo seed

## 3. Caching query layer (UI-3)

- [x] 3.1 Choose the layer (a query library or Nuxt-native keyed `useAsyncData` with `refreshNuxtData`) and add it to
  `apps/web`, with one composable per resource that derives the cache key from the resource and its parameters; verify
  `npm run typecheck` and `npm run build` pass
- [x] 3.2 Move every page off its ad-hoc `load()` onto the query layer, each mutation invalidating the keys it changes;
  verify a Playwright test citing UI-3 creates a bundle and sees it on the Composition grid without a reload
- [x] 3.3 Document the data-layer convention in `apps/web/README.md` (or the frontend section of `CONTRIBUTING.md`) and
  verify `uv run rumdl check .` passes

## 4. Validation from the OpenAPI constraints (UI-4)

- [x] 4.1 Publish the reserved endpoint names in the endpoint name's schema (from `domain/shared/resource_names.py`, so
  the list has one source) and regenerate with `cd apps/web && npm run openapi`; verify a backend test asserts the
  published schema rejects every reserved name and the existing EP tests still pass
- [x] 4.2 Generate the frontend validators from `apps/web/openapi.json` (patterns, the `__` rule, reserved names) and
  replace the hand-copied regexes in `app/utils/resourceNames.ts`, removing its stale `models/base.py` reference;
  verify a unit or Playwright test citing UI-4 for each rule, including `Upstream name must not contain "__"`
- [x] 4.3 Check name uniqueness against the cached list of the same resource before submitting; verify a Playwright
  test citing UI-4 sees the *taken* message for an existing bundle name with no request sent

## 5. API keys: scope and re-activation (UI-1)

- [x] 5.1 Add `POST /api/v1/api-keys/{id}:activate` to the API-key controller and service, publishing an `api_key`
  invalidation event like deactivation; verify an API test citing UI-1/AUTH-25 that a re-activated key authenticates
  again, then run `cd apps/web && npm run openapi`
- [x] 5.2 Add the endpoint-scope picker (endpoint-kind keys only) and the scope column to `pages/api-keys.vue`, and the
  *Re-activate* action on inactive rows; verify Playwright tests citing UI-1 for both scenarios
- [x] 5.3 Document scoping and re-activation in `docs/manage/api-keys.md` and the management API's action list in
  `docs/integrate/management-api.md`; verify `python3 tools/check_docs_links.py` passes

## 6. Curation, stale tools and audit (UI-1; after complete-tool-curation and harden-audit-log)

- [x] 6.1 Once complete-tool-curation lands, add *stale* badges and *Refresh & prune* to the upstream detail page and
  description/annotation override editing plus *stale* badges to the bundle curation table; verify Playwright tests
  citing UI-1 and BND-16
- [x] 6.2 Once harden-audit-log lands, add the bundle, upstream and caller filters to `pages/audit.vue` and download the
  CSV from the full filtered result; verify a Playwright test citing UI-1/OPS-6 that the CSV holds more rows than the
  loaded page
- [x] 6.3 Update `docs/manage/servers.md`, `docs/manage/bundles.md` and `docs/manage/audit.md` and re-run
  `npm run docs:screenshots`; verify the docs build passes

## 8. Gates

- [x] 8.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .` and `uv run lint-imports`; verify all
  pass
- [x] 8.2 Run `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py` and
  `check_adr_graph.py`; verify all pass
- [x] 8.3 Run `cd apps/web && npm run openapi && npm run typecheck && npm run build` and verify `git diff` shows no
  drift in `openapi.json` / `types/api.d.ts`
- [x] 8.4 Run `openspec validate --all --strict` and verify it passes
