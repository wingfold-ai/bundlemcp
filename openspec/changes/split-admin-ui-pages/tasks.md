# Tasks

## 1. Test harness and CI (UI-13)

- [x] 1.1 Add `vitest`, `@nuxt/test-utils` and `happy-dom` (latest stable) as dev dependencies of `apps/web`, a
      `"test": "vitest run"` script, and `apps/web/vitest.config.ts` built with `defineVitestConfig`, collecting
      `apps/web/unit/**/*.test.ts`. Verify with `npx vitest list` loading the config without error, and with
      `npx playwright test --list` listing no file from `apps/web/unit/`
- [x] 1.2 Add unit tests for the existing utils under `apps/web/unit/utils/`:
  - `resourceNames.test.ts`, named `UI-4 …`: pattern, `__` in an upstream name, a reserved endpoint name, a taken name.
  - `schemaForm.test.ts`, named `UI-9 …`: flat schema to fields, nested schema to null, form values to arguments and
    back.
  - `renderPromptText.test.ts`, named `BND-20 …`: substitution, a missing value becomes empty, a substituted value is
    not rescanned, the placeholder list.

  Verify with `npm test`
- [x] 1.3 Add `apps/web/unit/composables/useQuery.nuxt.test.ts`, named `UI-3 …`. It checks that a cached result is
  returned on a second use, that `invalidate("bundles")` drops `bundles` and `bundles:x:tools` but not `endpoints`, and
  that a manual refresh bypasses the cache. Verify with `npm test`
- [x] 1.4 Let `apps/web/tests/spec-map.ts` also read `## ADDED Requirements` from `openspec/changes/*/specs/*/spec.md`
  (excluding `archive/`), with the main specs taking precedence. Verify with `npm run test:map`, which regenerates
  `TESTMAP.md` unchanged, and with a scratch `requirement("UI-12")` call resolving while this change is open
- [ ] 1.5 In `.github/workflows/ci.yml`:
  - integration job: replace `npx playwright test oauth-consent.spec.ts` with
    `npx playwright test --grep-invert @fleet`, rename the step `Admin UI browser suite (UI-13)`, and upload
    `apps/web/playwright-report` as an artifact on failure;
  - frontend job: add `UI unit tests (UI-13)` running `npm test`.

  Do not edit the DEP-10 requirement. Verify with the pull request's CI: all thirteen specs run and pass on the
  unchanged pages. Fix each failure in the spec or its seed, never with a skip, and record the suite's duration in the
  PR
- [x] 1.6 Document `npm test` and the CI coverage in `CONTRIBUTING.md` (the browser-test paragraph) and
  `deploy/TESTING.md`. Verify with `uv run rumdl check CONTRIBUTING.md deploy/TESTING.md` and
  `python3 tools/check_docs_links.py`

## 2. Shared pieces and generated types

- [x] 2.1 Add `useProfiles()` to `composables/useManagementQueries.ts`, returning `EndpointProfileRead[]` under
  `queryKeys.profiles`. Use it in `pages/bundles/[name].vue` and `pages/endpoints/[name].vue`, and delete both
  `ProfileInfo` interfaces and their `as ProfileInfo[]` casts. Verify with `npm run typecheck` and
  `grep -rn "ProfileInfo" apps/web/app` returning nothing
- [x] 2.2 Type the upstream page's refs with `ServerAuthMode`, `ListingSnapshotMode`, `IdentityMode` and `UpstreamGrant`
      from `components["schemas"]`, and drop the `as typeof …value` casts in `seedServer`. Verify with
      `npm run typecheck` and with `grep -rn 'ref<"' apps/web/app/pages/upstreams apps/web/app/components/Upstream*`
      returning nothing
- [x] 2.3 Add `upstreamCallbackUrl()` beside `apiBase()` in `composables/useApi.ts`, and use it in both places that
  build the callback URL. Verify with `npm run typecheck` and with `grep -rn "oauth/upstream/callback" apps/web/app`
  matching only `useApi.ts`
- [ ] 2.4 Add `utils/headerRows.ts` (`HeaderRow`, `rowsToHeaders(rows, { emptyValue: "keep" | "key" })`) with
  `unit/utils/headerRows.test.ts`, named `UI-1 …`: blank keys dropped, keys trimmed, and both empty-value rules. Add
  `components/HeaderRowsEditor.vue` (`v-model`, placeholder, input-type, test-id-prefix and button-label props), and
  use it for the forward and static headers on the upstream page and the forward headers in `ServerRegistration.vue`.
  Verify with `npm test`, and with Playwright `gsc-upstream.spec.ts` (E2E-12 still finds `fwd-key-0`) and
  `server-flow.spec.ts`
- [x] 2.5 Add `composables/useAction.ts` (`useAction(fn, { invalidates })` → `{ run, busy, error }`, plus
  `ValidationProblem`) with `unit/composables/useAction.nuxt.test.ts`, named `UI-12 …`. The tests cover: a validation
  problem sets `error` and sends nothing; an API error sets `error`; a success clears `error` and invalidates the named
  resources; a second `run` clears the previous error. Verify with `npm test`
- [ ] 2.6 Add `authedFetch` to `composables/useApi.ts`, sharing the `401`/`403` handling with the `openapi-fetch`
  middleware through one function. Verify with `npm run typecheck` and with `inspector.spec.ts` (E2E-37) still passing

## 3. Rename card

- [ ] 3.1 Add `components/RenameCard.vue` (props `kind`, `current`, `taken` and `requireAcknowledgement`, a
  `consequence` slot, a `renamed` event, and its own `useAction`). Use it on the bundle page (acknowledgement
  required), on the endpoint page (acknowledgement required, the before/after URL in the slot) and in the upstream
  danger zone (acknowledgement optional, sends `force`). Pass the taken names on the upstream page, too. Verify with
  Playwright: the existing bundle and endpoint rename scenarios in `bundle-flow.spec.ts` and
  `endpoint-config.spec.ts`; a new scenario `E2E-38` in `server-flow.spec.ts` citing UI-4, in which typing an existing
  upstream's name as the new name shows the taken-name hint and sends no request; and `npm run test:map`

## 4. Bundle detail page (UI-12)

- [x] 4.1 Add `composables/useEditableRows.ts` for the curation drafts (`rowOf`, `sameRow` and the server-reseed
  watch, moved from `pages/bundles/[name].vue:266-300`) with `unit/composables/useEditableRows.nuxt.test.ts`, named
  `BND-16 …`. The tests check that a reseed keeps an unsaved draft and replaces a saved one. Verify with `npm test`
- [ ] 4.2 Split `pages/bundles/[name].vue` into `BundleMetaCard`, `BundleMembersCard`, `BundleToolCuration`,
  `BundleEndpointsCard` and `EndpointCreateForm`, plus the `RenameCard` from 3.1. Each card has its own `useAction`, an
  error element marked `data-testid="error"` inside the card, and a `data-testid="card-<name>"` on the card. The page
  keeps only the loads, the not-found state and the load error. Verify with `npm run typecheck`, `npm run build`, the
  bundle page at no more than 200 lines (`wc -l`), and the unchanged Playwright `bundle-flow.spec.ts` and
  `curation.spec.ts`
- [ ] 4.3 Add Playwright scenarios citing UI-12 in `curation.spec.ts`, with entries in `spec-map.json` and
  `npm run test:map`:
  - `E2E-39`: a non-object annotation override shows its error inside `card-curation` and nowhere else.
  - `E2E-40`: a member toggle refused with `409` (forced with `page.route`) shows its error on `card-members`, and it
    stays there while a successful meta save shows none on `card-meta`.
  - `E2E-41`: a load failure of the bundle's tools, forced with `page.route` answering `500`, shows at the page top.

  Verify with `npx playwright test curation.spec.ts`

## 5. Upstream detail page and registration (UI-12)

- [ ] 5.1 Split `pages/upstreams/[name].vue` into `UpstreamConfigCard`, `UpstreamToolsCard`, `UpstreamOAuthCard` and
  `DangerZoneCard`, each with its own `useAction` and in-card error. Verify with `npm run typecheck`,
  `npm run build`, the page at no more than 200 lines, and the unchanged `server-flow.spec.ts` and
  `gsc-upstream.spec.ts`
- [ ] 5.2 Add Playwright scenario `E2E-42` in `server-flow.spec.ts`, citing UI-12 and UPS-5. Renaming `echo` (a
  bundle member) without the acknowledgement shows the API's refusal inside `card-danger`, and `card-config` shows
  none. Add its `spec-map.json` entry and run `npm run test:map`. Verify with `npx playwright test server-flow.spec.ts`
- [ ] 5.3 Extract `composables/useServerInspection.ts` and `components/CredentialSourcePicker.vue` from
  `ServerRegistration.vue`, keeping its one error element (it is a single card). Verify with `npm run typecheck`,
  `ServerRegistration.vue` at no more than 300 lines, and the unchanged `server-flow.spec.ts` (E2E-03, E2E-04, E2E-31,
  E2E-32)

## 6. Endpoint detail page and inspector

- [ ] 6.1 Give each section of `pages/endpoints/[name].vue` (configuration, danger zone) its own `useAction` and
  in-card error, and add `data-testid="card-<name>"`. Verify with `npm run typecheck` and the unchanged
  `endpoint-config.spec.ts` (E2E-08, E2E-22, E2E-26)
- [ ] 6.2 Extract `composables/useToolCall.ts` (stream, progress, outcome and failure, over `authedFetch`) and
  `components/ToolArgumentsEditor.vue` (form and raw JSON) from `pages/inspector.vue`. Verify with
  `npm run typecheck`, `inspector.vue` at no more than 250 lines, and the unchanged `inspector.spec.ts` (E2E-37)

## 7. Gates

- [x] 7.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .` and `uv run lint-imports`; all must be
  clean
- [x] 7.2 Run `python3 tools/check_docs_links.py`, `python3 tools/check_docs_symbols.py`,
  `python3 tools/check_docs_settings.py`, `python3 tools/check_adr_graph.py`, `python3 tools/check_compose_ports.py` and
  `python3 tools/check_spec_ids.py`; all must pass. The last also confirms that no `.ts` or `.vue` comment cites a code
- [x] 7.3 Run `cd apps/web && npm run openapi && npm run typecheck && npm run build && npm test`, with Node ≥ 24.
  `git diff --exit-code apps/web/openapi.json apps/web/types/api.d.ts` must show no change
- [ ] 7.4 Run `cd apps/web && npx playwright test --grep-invert @fleet` against
  `docker compose -f deploy/docker-compose.yml up -d --build --wait`; every scenario must pass, E2E-38 to E2E-42
  included. Run `npm run test:map` and confirm `TESTMAP.md` is committed
- [x] 7.5 Run `openspec validate --all --strict`; it must pass
