# Proposal

## Why

The management API is the contract registrars, scripts and the admin UI build on, and a few of its routes and
responses drifted from what an earlier draft specified: the profile list under `/api/v1/endpoints/profiles` rather than
`/api/v1/profiles`, no per-upstream `:probe` action, no tool cache in the registrar upsert, list ordering that differs
per resource. Two gaps are real: a wrong `transport` gets Pydantic's generic literal error, which does not tell a
registrar what to send, and the endpoint rename explains its consequence only after the attempt fails with `409`.

## Decisions

Settled by the maintainers on 2026-10-15, each item either built or amended to what exists:

- **Profiles route: amended.** The profile list stays at `GET /api/v1/endpoints/profiles`, which the main spec already
  names; no alias, no breaking removal.
- **`:probe`: amended.** `:refresh-tools` already contacts the upstream synchronously and reports the outcome; a
  connect-only probe is not added.
- **Tool cache in the upsert response: amended.** The cache stays at `upstreams/{name}/tools`, where it is paginated;
  embedding it would make the upsert response unbounded.
- **Ordering: amended.** The main spec already documents what exists (registry resources by creation time then id,
  audit records newest first, a bundle's prompts and resources by name, as BND-25/BND-26 serve them).
- **Built:** the pointed `transport` message (MGMT-4) and the rename UI that states the consequence first (EP-8).

## What Changes

- **MGMT-4:** an unsupported `transport` answers a 422 whose message names the field and the one supported value.
- **EP-8:** the endpoint rename UI shows the current and resulting URL and the client-breaking consequence before the
  attempt, and enables the rename only after the admin acknowledges it (today a bare `force` checkbox).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `management`: MGMT-4 (pointed `transport` error).
- `endpoints`: EP-8 (the UI states the rename consequence before the attempt).

## Impact

- **API:** the `transport` 422 message changes. Regenerate `apps/web/openapi.json` and `apps/web/types/api.d.ts` if
  the schema changes.
- **Code:** `application/schemas/servers/server_upsert.py`, `apps/web/app/pages/endpoints/[name].vue`.
- **Docs:** `docs/integrate/management-api.md`, `docs/manage/endpoints.md`.
