# Design

## Context

See proposal.md for the motivation. Everything here is in `apps/web` (Nuxt 4, Nuxt UI v4), outside the Python layers.
The layer rules of CLAUDE.md do not apply to it. The frontend's own rule does: the UI is a pure client of the
management API, with every DTO type generated from OpenAPI (UI-3).

The current state the design works from:

- **One error ref per page.** `pages/bundles/[name].vue:12` declares `const errorMsg = ref("")`. All five cards write
  to it:
  - meta, `:97`
  - rename, `:161`
  - members, `:200`, `:213`, `:225` and `:241`
  - curation, `:311` and `:322`
  - endpoint create, `:401`

  The page renders it once at the top (`:431`). `pages/upstreams/[name].vue:12` and `:341` do the same for four cards,
  and so does `pages/endpoints/[name].vue:35` and `:223`. The bundle page's own prompt and resource cards already keep
  their own error (`components/BundlePrompts.vue:28`), and this design follows that precedent.
- **Hand-written types.**
  - `ProfileInfo` is declared at `pages/bundles/[name].vue:349` and `pages/endpoints/[name].vue:9`, and cast with
    `as ProfileInfo[]` at `bundles/[name].vue:56` and `endpoints/[name].vue:32`. Yet the route is already typed:
    `types/api.d.ts:5037` answers `components["schemas"]["EndpointProfileRead"][]`.
  - The four unions at `pages/upstreams/[name].vue:61-64` and `:203` restate `ServerAuthMode`,
    `ListingSnapshotMode`, `IdentityMode` and `UpstreamGrant` (`types/api.d.ts:3248`, `:2707`, `:2416`, `:3742`).
- **Duplicated logic.**
  - Header rows: `{ key, val }[]` editors at `upstreams/[name].vue:66-68`, `:86-92`, `:441-498` and
    `components/ServerRegistration.vue:46`, `:98`, `:546-551`.
  - `callbackUrl`: `upstreams/[name].vue:280` and `ServerRegistration.vue:77`.
  - The profiles query: `bundles/[name].vue:54` and `endpoints/[name].vue:30`.
  - Three rename flows:
    - `bundles/[name].vue:140-190` acknowledges and resets on a name change, and checks taken names.
    - `endpoints/[name].vue:165-200` does the same.
    - `upstreams/[name].vue:283-320` has a `renameForce` that never resets, and no taken-name check, although UI-4
      requires one.
- **The streamed call.** `pages/inspector.vue:178` calls `fetch` directly and handles only `401` (`:184`). The
  403-demotion check in `composables/useApi.ts:20-26` never sees this call.
- **CI.** The integration job runs `npx playwright test oauth-consent.spec.ts` (`.github/workflows/ci.yml:214`), after
  the stack and the Python integration suite. `tests/global-setup.ts` already signs in through the dev identity provider
  there. None of the thirteen specs uses a `fleet` service; each registers what it needs or uses the seeded `echo`.
  `tests/spec-map.ts:40-69` resolves requirement text only from `openspec/specs`, and `requirement()` throws on an
  unknown code (`:71-74`).

## Goals / Non-Goals

**Goals:**

- Each card owns its action state (busy flag and error), so UI-12 follows from the structure and is not maintained by
  hand.
- No hand-written DTO type or cast remains in the pages this change touches.
- Each duplicated piece has one home, and the pure parts of it are unit-tested.
- CI exercises the browser suite and the unit tests on every pull request (UI-13).

**Non-Goals:**

- No visual redesign, and no `data-testid` renames beyond the per-card error markers. Existing scenarios keep their
  selectors.
- No change to the pages this change does not split (API keys, users, settings, audit, logs, catalogue).
- No shared endpoint-auth-mode helper. `toggleAuthMode` exists on both the bundle page and the endpoint page, but
  merging the endpoint create form with the endpoint configuration form is a separate change.
- No component-mount tests. Vitest covers utils and composables; the cards are covered by Playwright.

## Decisions

### Per-card state through `useAction`

A new composable in `composables/useAction.ts` (N19's `useMutation`, named for what the cards call it):
`useAction(fn, { invalidates })` returns `{ run, busy, error }`.

- `run` clears `error`, sets `busy` and awaits `fn`.
- On a `{ error }` result or a thrown `ValidationProblem`, it stores the message through `apiErrorMessage`.
- On success it calls `invalidate(...invalidates)`.

A card makes one `useAction` per button and renders the error inside its own `UCard` as
`<p data-testid="error">`, with the card itself marked `data-testid="card-<name>"`.

Client-side validation throws a `ValidationProblem` (one small class in the same module) instead of writing to a ref.
That is how a validation error and an API error land in the same place.

Alternatives considered:

- **Keep one ref and add a "source" field.** It keeps the global state and the top-of-page render, and every card
  must still remember to set the source.
- **Toasts (`useToast`).** A toast is detached from the card and disappears on its own. A validation error that blocks
  a submit has to stay visible.

### The card split

The pages become thin shells: they read the route, load the shared data, render the not-found and load-error states,
and lay out the cards. Each card gets its props and owns its forms and actions.

| Page | Cards (`components/`) | Composables |
|---|---|---|
| `bundles/[name].vue` | `BundleMetaCard`, `RenameCard`, `BundleMembersCard`, `BundleToolCuration`, `BundleEndpointsCard` (with `EndpointCreateForm`) | `useEditableRows` (curation row drafts: `rowOf`/`sameRow`, `:266-300`) |
| `upstreams/[name].vue` | `UpstreamConfigCard` (with `HeaderRowsEditor` ×2), `UpstreamToolsCard`, `UpstreamOAuthCard`, `DangerZoneCard` (with `RenameCard`) | — |
| `endpoints/[name].vue` | the existing sections, each with its own `useAction`; danger zone uses `RenameCard` | — |
| `ServerRegistration.vue` | `CredentialSourcePicker`, `HeaderRowsEditor` | `useServerInspection` (URL check, `server.json` import, detection, `:128-190`) |
| `inspector.vue` | `ToolArgumentsEditor` (form ⇄ raw JSON, `:126-162`) | `useToolCall` (stream, progress, outcome, failure, `:164-203`) |

Card components live in `components/` and are auto-imported, as `MemberEntryCuration.vue` already is. Grouping them
in folders (`components/bundle/…`) was rejected: Nuxt would prefix the names (`BundleBundleMetaCard`), or the pages
would need explicit imports.

### Shared pieces

- **`HeaderRowsEditor.vue`** (`v-model` of `HeaderRow[]`): props for the placeholders, input type (password for the
  static headers), test-id prefix (`fwd`/`hdr`, so `fwd-key-0` keeps working for E2E-12) and add-button label.
  Converting rows to a header map is a pure function, `headerRows.ts`, in `utils/`:
  - `rowsToHeaders(rows, { emptyValue })` takes `"keep"` for the detail page, which sends `r.val` as typed
    (`upstreams/[name].vue:113-116`).
  - It takes `"key"` for registration, where an empty target defaults to the client header's name
    (`ServerRegistration.vue:214`).

  The two callers keep their current semantics. Unifying them would change what an existing save sends.
- **`upstreamCallbackUrl()`** in `composables/useApi.ts`, beside `apiBase()`. It is the gateway's URL, so it belongs
  with the function that knows the gateway origin.
- **`useProfiles()`** in `useManagementQueries.ts`, typed `EndpointProfileRead[]` under `queryKeys.profiles`.
- **`RenameCard.vue`**: props `kind: NamedResource`, `current`, `taken: string[]` and `consequence` (a slot for the
  per-resource warning and, for endpoints, the before/after URL that EP-8 requires), plus `requireAcknowledgement`.
  - With `requireAcknowledgement`, the button is disabled until the box is ticked (bundles: BND-10; endpoints: EP-8).
  - Without it, ticking the box only sends `force` (upstreams: UPS-5, where force matters only for a bundle member).
  - The acknowledgement resets on every change of the new name, in all three cases.
  - The card emits `renamed(newName)`; the page does the invalidation and the navigation.

### Generated types

- `ProfileInfo` is deleted. `useProfiles()` returns the generated type, so both casts disappear.
- The upstream config card types its refs as `Schemas["ServerAuthMode"]` and so on. `seedServer`'s
  `as typeof authMode.value` casts (`upstreams/[name].vue:74-75`) go too, because `ServerRead` already carries the
  enum types.
- A `grep` for `interface .*Info\b` and `as .*\[\]` in `app/` is part of the verification.

### The streamed call: `authedFetch`

`useApi.ts` gains `authedFetch(path, init)`. It applies `credentials: "include"` and the same `onResponse` handling
the `openapi-fetch` middleware uses: on `401` it calls `gotoLogin()`, and on a `403` from a user who is no longer an
admin it sends them to `/catalogue`. Both paths call one function, so they cannot drift. `useToolCall` uses it.

### Vitest

- Dev dependencies: `vitest`, `@nuxt/test-utils` and `happy-dom`, at their latest stable versions. The `test` script
  is `vitest run`.
- `vitest.config.ts` uses `defineVitestConfig` from `@nuxt/test-utils/config`, so the `~`/`~~` aliases and the
  `openapi.json` import of `utils/resourceNames.ts` resolve as they do in the app.
- Tests live in `apps/web/unit/`, not in `tests/` and not beside the sources:
  - Playwright's `testDir: "./tests"` (`playwright.config.ts:13`) would collect a `*.test.ts` file there.
  - Nuxt auto-imports every top-level file in `app/utils/` and `app/composables/`, so a test file beside the sources
    would be scanned as a module.
- Pure tests (`unit/utils/*.test.ts`) run in the default Node environment. Tests that need a Nuxt app
  (`unit/composables/*.nuxt.test.ts`, for `useQuery`/`invalidate` and `useAction`) use the `nuxt` environment, which
  `@nuxt/test-utils` selects by the `.nuxt.test.ts` suffix.
- Test names cite the requirement they verify, for example `describe("UI-4 nameProblem", …)`. Comments cite none.

### CI

- **Integration job:** replace `npx playwright test oauth-consent.spec.ts` (`ci.yml:214`) with
  `npx playwright test --grep-invert @fleet`, in a step named `Admin UI browser suite (UI-13)`. No spec carries `@fleet`
  today; the marker is there for the first one that needs private images. The HTML report is uploaded as an artifact on
  failure.
- **Frontend job:** add a step `UI unit tests (UI-13)` running `npm test` after the build.
- The DEP-10 requirement text is not touched. Its owner is `gate-supply-chain-in-ci`.

### Requirements of an open change in `spec-map.ts`

New scenarios cite UI-12 and UI-13, which reach `openspec/specs` only at archive. `requirement()` would throw before
then and fail every run. `allRequirements()` therefore also reads `## ADDED Requirements` blocks from
`openspec/changes/*/specs/*/spec.md`, excluding `archive/`. A code in the main specs wins over a delta.
`check_spec_ids.py` already treats open-change codes as defined, so the two agree.

## Risks / Trade-offs

- [Risk] The twelve specs that never ran in CI fail there, because of timing, a missing seed, or state left behind by
  the Python integration suite, which runs first against the same stack. → Mitigation: run the whole suite in CI on the
  branch before the split starts (task 1.5). Fix what fails in the spec or its seed, never with a skip. If a spec
  truly needs local-only state, tag it `@fleet` and name the reason in the PR. Playwright keeps `workers: 1` and
  `trace: "retain-on-failure"`, and the report is uploaded.
- [Risk] The integration job gets longer. → Mitigation: the suite runs with one worker and no video. Task 1.5 records
  its CI duration in the PR; the time is accepted for the coverage and not parallelised, since the stack is stateful.
- [Risk] A refactor this size silently changes behaviour. → Mitigation: the split goes page by page. Each group runs
  the existing Playwright scenarios for that page before and after, and keeps the `data-testid` markers. Behaviour
  changes are limited to UI-12, the upstream rename card (taken-name check, acknowledgement reset) and N20.
- [Risk] `getByTestId("error")` becomes ambiguous once several cards can each render one. → Mitigation: only one card
  shows an error after a single failed action, so existing assertions still match. New assertions scope through the
  card (`getByTestId("card-curation").getByTestId("error")`), and the error element renders only while it has text.
- [Risk] `@nuxt/test-utils` lags a Nuxt major. → Mitigation: only the composable tests need it. If it does not yet
  support the installed Nuxt, those tests fall back to the documented Nuxt mocks, and the util tests are unaffected.
- [Trade-off] `rowsToHeaders` keeps two empty-value rules instead of one. That is honest about today's behaviour, but
  the question stays open (see Open Questions).

## Migration Plan

Frontend only. The change ships with the web image and has no data, API or configuration migration. Rollback is a
revert of the web image.

## Adjustments made during implementation

- **One action per card, not per button.** UI-12 says starting another action on a card clears that card's error.
  With one `useAction` per button, a second button would leave the first one's error standing. A card with several
  buttons therefore uses `useCardAction()` (in `useAction.ts`): one `useAction` whose argument is the call each button
  makes, so the card has one busy flag and one error. Invalidation that differs per button runs after `run` reports
  success. Single-button cards still call `useAction(fn, { invalidates })` directly.
- **`DangerZoneCard` serves both the upstream and the endpoint page.** Both danger zones are a rename plus a delete;
  the card embeds `RenameCard`, owns the delete, and clears the rename's error when a delete starts (and the other way
  round), so the card keeps one error state. The endpoint page passes its before/after URL through the slot. The
  bundle page keeps `RenameCard` as a card of its own, marked `card-rename`; the unused `bundle-rename-card` marker
  goes.
- **`RenameCard` trims the new name and disables Rename while a hint shows**, on all three pages. The endpoint page
  used to enable the button and report the same problem on click.
- **Line budgets needed two more extractions each.** The planned extractions left `ServerRegistration.vue` at 378
  lines and `inspector.vue` at 305:
  - `InspectionSummary.vue` (what the URL check found) and `UpstreamProtocolSettings.vue` (protocol and listing
    selects, which the upstream configuration card repeated verbatim and now shares);
  - `InspectorToolPanel.vue`: the selected tool, its arguments, the call and its result, owning `useToolCall`.
- **E2E-42 renames a dedicated upstream**, not `echo`: if the guard ever let the rename through, the seed every other
  scenario relies on would be renamed.
- **`TESTMAP.md`** was already stale on `main` (the UPS-10 text that #168 changed); `npm run test:map` refreshes it.

## Open Questions

- Should an empty forward-header target mean "same name" on the detail page too, as it does in registration? Today a
  detail-page save sends `{"x-foo": ""}`. Answering it changes one option value in `UpstreamConfigCard`, not this
  design. Implemented as designed: both behaviours stay, chosen by `rowsToHeaders`' `emptyValue` option.
