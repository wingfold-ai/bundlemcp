# Proposal: complete the admin UI

## Why

The admin UI covers most of the management surface, but several parts of the original admin-ui spec were never built
or were built differently: API keys cannot be scoped to endpoints or re-activated from the UI, pages reload by hand
instead of sharing a cached, invalidated query layer, the client-side validation is a hand-copied set of regexes (whose
source comment points at a module that no longer exists), and some copy still says a bare *server*, including the detail
page's title. The main spec was narrowed to what exists; this change restores the intended behaviour.

## What Changes

- **API keys page:** an endpoint-scope picker for endpoint-kind keys, the scope shown in the list, and a *Re-activate*
  action for an inactive key, backed by a new `POST /api/v1/api-keys/{id}:activate` action.
- **Upstream detail page:** a *Refresh & prune* action and *stale* badges on discovered tools, once the backend offers
  them ([complete-tool-curation](../archive/2026-10-13-complete-tool-curation/proposal.md)).
- **Bundle detail page:** curation table edits description and annotation overrides and flags stale tools (BND-16, from
  complete-tool-curation).
- **Audit page:** filters for bundle, upstream and caller as well as endpoint, status, tool and time range, and a CSV
  export of the whole filtered result (OPS-6, from [harden-audit-log](../harden-audit-log/proposal.md)).
- **Non-admin access (UI-2):** a signed-in non-admin who opens a management page sees a *no access* page that links to
  the catalogue, instead of a silent redirect — see the open decision.
- **Data layer (UI-3):** query results are cached by key and a mutation invalidates every cached query it affects, so
  all views of the changed data refresh without per-page `load()` calls.
- **Validation (UI-4):** client-side rules are generated from the constraints published in the OpenAPI document
  (including the reserved endpoint names, which are not published today), and name uniqueness is checked against the
  existing resources before submitting.
- **Naming (UI-7):** page titles, buttons, empty states and error copy never say a bare *server*; the detail page is
  titled *Upstream server: {name}*.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `admin-ui`: UI-1 (API-key scope and re-activation, refresh & prune, stale badges, richer audit page), UI-2 (no-access
  page for non-admins), UI-3 (caching and invalidation layer), UI-4 (validation generated from the OpenAPI constraints,
  uniqueness checked before submit), UI-7 (no bare *server* in any copy).

## Open decision

- **UI-2 — no-access page or redirect.** Today a non-admin is redirected to `/catalogue` from any management page, and
  the Playwright suite (`apps/web/tests/catalogue.spec.ts`) asserts that redirect. The original spec asked for a "no
  access" page; the delta here specifies one that links to the catalogue. Alternative: **amend** — drop the UI-2 delta
  from this change and keep the redirect the main spec already describes. Maintainers decide before applying; the
  recommendation of the gap report was to amend.

## Impact

- **Depends on** [complete-tool-curation](../archive/2026-10-13-complete-tool-curation/proposal.md) (refresh & prune,
  stale tools, description and annotation overrides — BND-16, UPS-19) and
  [harden-audit-log](../harden-audit-log/proposal.md) (the bundle, upstream and caller filters and the full-result CSV —
  OPS-6). The UI-1 parts that rely on them land after those changes; the rest of this change does not wait.
- **Coordination:** the per-server *probe* action of the original UI-1 is the *Refresh tools* action that already
  re-probes; a separate `:probe` route is decided in [align-management-api](../align-management-api/proposal.md)
  (MGMT-1). The Settings page's export/import belongs to [add-export-import](../add-export-import/proposal.md)
  (MGMT-22); the *Live logs* and *Inspector* pages to [add-live-logs](../add-live-logs/proposal.md) and
  [add-inspector](../add-inspector/proposal.md).
- **API:** a new `POST /api/v1/api-keys/{id}:activate` action (publishes an invalidation event like deactivation). The
  management API's action list (MGMT-1) is modified by align-management-api; whichever change lands second adds
  `:activate` to it.
- **OpenAPI:** the reserved endpoint names become part of the published schema; `apps/web/openapi.json` and
  `apps/web/types/api.d.ts` are regenerated.
- **Frontend:** `apps/web/app/pages/*`, `app/components/ServerRegistration.vue`, `app/utils/resourceNames.ts`, a new
  query/caching dependency or a Nuxt-native equivalent, and the Playwright suite (`apps/web/tests/`).
- **Docs:** `docs/manage/api-keys.md`, `docs/manage/servers.md`, `docs/manage/audit.md` and the docs screenshots.
