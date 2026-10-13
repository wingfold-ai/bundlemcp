# Proposal

## Why

The management API is the contract registrars, scripts and the admin UI build on, and a few of its routes and
responses drifted from what was specified: the profile list lives under `/api/v1/endpoints/profiles` instead of
`/api/v1/profiles`, there is no per-upstream `:probe` action, the registrar upsert does not return the tool cache, a
wrong `transport` gets Pydantic's generic literal error, list ordering differs per resource, and the endpoint rename
explains its consequence only after the attempt fails with `409`. Each item is either built here or the spec is amended
to the routes that exist; the maintainers decide which before this change is applied.

## What Changes

- **MGMT-1:** serve the profile list at `GET /api/v1/profiles`, and add `POST /api/v1/upstreams/{name}:probe`, which
  contacts the upstream now (connection, protocol, `connection_state`, health) without re-listing its tools.
- **MGMT-4:** `PUT /api/v1/upstreams/{name}` returns the server together with its current tool cache, and an
  unsupported `transport` answers a 422 whose message names the field and the one supported value.
- **MGMT-5:** every list route orders by creation time then id (audit records newest first), including a bundle's
  prompts and resources, which today page by name.
- **EP-8:** the endpoint rename UI shows the current and resulting URL and the client-breaking consequence before the
  attempt, and enables the rename only after the admin acknowledges it (today a bare `force` checkbox).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `management`: MGMT-1 (profiles route, `:probe` action), MGMT-4 (tool cache in the upsert response, pointed
  `transport` error), MGMT-5 (uniform ordering).
- `endpoints`: EP-8 (the UI states the rename consequence before the attempt).

## Open decision

Each item below is either **built** (the delta as written) or **amended** (the delta is replaced by wording that
describes what exists). The maintainers decide per item before applying:

1. **MGMT-1 profiles route.** Build: add `GET /api/v1/profiles`; keep `GET /api/v1/endpoints/profiles` as a deprecated
   alias for one release so the UI and scripts can move, then remove it (**BREAKING** at removal). Amend: keep
   `endpoints/profiles` and drop the profiles part of the delta (the main spec already names it).
2. **MGMT-1 `:probe`.** Build: a connect-only probe as specified. Amend: `:refresh-tools` already contacts the upstream
   synchronously and reports the outcome, so `:probe` is redundant; drop it from the delta.
3. **MGMT-4 tool cache in the upsert response.** Build as written. Amend: keep "the tool cache is read from
   `upstreams/{name}/tools`" — the cache is paginated there, and embedding it makes the upsert response unbounded.
   The pointed `transport` message should be built either way.
4. **MGMT-5 ordering — likely amend.** The main spec already documents what exists (audit newest first; a bundle's
   prompts and resources by name), and name order is what BND-25/BND-26 serve to clients and what
   `docs/manage/bundles.md` documents. Amending means dropping the MGMT-5 delta entirely. Building means changing the
   two repositories' page order and the docs, while `prompts/list` on an endpoint keeps name order.

EP-8 has no open decision.

## Impact

- **API:** `GET /api/v1/profiles` (new, plus deprecated alias), `POST /api/v1/upstreams/{name}:probe` (new),
  `ServerRead` in the upsert response gains a `tools` list (or a dedicated `ServerUpsertRead`), the `transport` 422
  message changes, bundle prompt/resource pages change order. Regenerate `apps/web/openapi.json` and
  `apps/web/types/api.d.ts`.
- **Code:** `api/management/controllers/` (a `ProfileController`, a probe handler on `ServerController`),
  `application/management/server_service.py`, `application/schemas/servers/`, the bundle prompt and resource
  repositories (on "build" for MGMT-5), and `apps/web/app/pages/endpoints/[name].vue`, `bundles/[name].vue` (profile
  route).
- **Docs:** `docs/integrate/management-api.md`, `docs/manage/endpoints.md`, `docs/manage/servers.md`,
  `docs/manage/bundles.md`.
- **Related changes:** [add-profile-interface](../archive/2026-10-13-add-profile-interface/proposal.md) moves the
  profile list into a service — whichever lands second wires the new route to it. `:probe` counts toward `health_status`
  through the shared count of [complete-upstream-health](../complete-upstream-health/proposal.md); built earlier, it
  uses the discovery service's failure recording. [complete-admin-ui](../complete-admin-ui/proposal.md) owns UI-2, which
  MGMT-1 references.
