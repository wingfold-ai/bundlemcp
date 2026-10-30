# Proposal

## Why

The admin UI's detail pages have grown into a few very large single-file components. Each one keeps a single error
message for the whole page, which causes a user-visible bug: on a bundle's page, a failed member toggle or a bad
curation override shows its error at the top of the page, far from the card the admin is working in. The same code also
hand-writes types the generated API contract already provides, copies the same editor and query logic between pages,
and is barely tested in CI. CI runs only one of the thirteen Playwright specs and has no unit tests for the UI's pure
logic.

The 2026-10-29 code audit found this (findings S24–S27, with N19 and N20 folded in where the split touches them).

## What Changes

- **Errors where they happened** (UI-12, added):
  - On the bundle, upstream and endpoint detail pages, a failed action shows its error on the card whose action
    failed: validation errors and API errors alike.
  - A failed page load still shows at the top of the page.
  - Starting an action on one card clears only that card's error.
- **The admin UI is tested in CI** (UI-13, added):
  - The integration job runs the whole Playwright suite against the core stack it already starts, instead of only
    `oauth-consent.spec.ts`.
  - The frontend job runs a new Vitest suite. It covers the UI's pure logic (name validation, the tool-argument form,
    the prompt preview) and the query cache's invalidation.
  - The DEP-10 CI-gates requirement is not modified; that requirement belongs to `gate-supply-chain-in-ci`.
- **Generated types only** (UI-3, no text change): the hand-written `ProfileInfo` interface and its `as ProfileInfo[]`
  casts, and the hand-restated `ServerAuthMode`, `ListingSnapshotMode`, `IdentityMode` and `UpstreamGrant` unions, are
  replaced by the generated `components["schemas"][…]` types.
- **Oversized pages split** (no behaviour change except UI-12):
  - The bundle detail page becomes one card component per card: meta, rename, members, tool curation and endpoints.
  - The upstream detail page becomes configuration, tools, upstream OAuth and danger-zone cards.
  - Guided registration moves its inspection logic into a composable and its credential-source picker into a
    component.
  - The inspector moves its tool-call stream into a composable and its argument form into a component.
- **Duplicated logic shared**:
  - One header-row editor, used for both the forward-header and the static-header rows.
  - One upstream OAuth callback URL.
  - One profiles query, `useProfiles()`, beside the other management queries.
  - One rename card used for bundles, upstreams and endpoints.

  On the upstream page, the shared rename card now reports a name that is already taken before submitting, as UI-4
  already requires. It also resets the acknowledgement whenever the new name changes, as the bundle and endpoint
  pages already do.
- **Inspector calls use the shared API session handling** (N20): the streamed tool call goes through the same
  401-and-403 handling as every other management call. Today it handles 401 itself and skips the demotion check.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `admin-ui`: UI-12 (added: an action's error is shown on the card that ran it), UI-13 (added: the browser suite and
  the UI unit tests run in CI).

## Impact

- **Resolves:** audit findings S24, S25, S26 and S27 (2026-10-29), plus N19 and N20 on the pages this change splits.
  No GitHub issue.
- **Files:**
  - `apps/web/app/pages/bundles/[name].vue`, `pages/upstreams/[name].vue`, `pages/endpoints/[name].vue`,
    `pages/inspector.vue` and `components/ServerRegistration.vue`, split into new components under
    `apps/web/app/components/` and composables under `apps/web/app/composables/`.
  - `apps/web/app/composables/useManagementQueries.ts` (`useProfiles`) and `useApi.ts` (a shared authenticated
    `fetch` for the streamed call).
  - `apps/web/package.json` (Vitest and the Nuxt test utilities as dev dependencies, a `test` script),
    `apps/web/vitest.config.ts`, and unit tests under `apps/web/unit/`.
  - `apps/web/tests/` (per-card error assertions and new scenarios in `spec-map.json`; `spec-map.ts` also resolves
    requirements that open changes add).
  - `.github/workflows/ci.yml`: the integration job runs the whole Playwright suite, and the frontend job runs Vitest.
- **API:** none. No DTO or route changes, so `openapi.json` and `types/api.d.ts` stay as they are.
- **Docs:** `CONTRIBUTING.md` and `deploy/TESTING.md` (how to run the unit tests, and that CI runs the browser suite).
  CI writes the CHANGELOG entry (DEP-12). No ADR: this restructures the frontend within the existing architecture.
- **Not covered:** the `busy`/`errorMsg` pattern on the pages this change does not split (API keys, users, settings,
  audit, logs, the bundle prompt and resource cards) keeps its current form. Those pages have one card or already
  keep their own error, so they have no misplaced error to fix.
