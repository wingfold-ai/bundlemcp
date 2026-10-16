# Proposal

## Why

There is no way to take a gateway's configuration out or move it to another instance: `docs/self-hosting/operations.md`
tells operators to fall back to a bootstrap file written by hand, and the only trace of the planned feature is an
`# MGMT-17` comment on the bootstrap document's `version` field. metamcp had a one-click export/import
(`../metamcp/apps/frontend/app/[locale]/(sidebar)/mcp-servers/export-import-buttons.tsx`); admins use it for backups,
for moving a setup from staging to production, and for producing the first bootstrap file.

## What Changes

- `GET /api/v1/export` returns a version-1 JSON document of all configuration by natural key — upstreams, bundles with
  membership, enable flags, tool curation, prompts and resources, and endpoints — valid as a bootstrap document.
- Secrets are exported as named `{"$secret": "<NAME>"}` placeholders unless `?include_secrets=true` is passed by an
  admin session; that export is audit-logged and carries a `warning` field. On import, a placeholder keeps the target's
  stored value.
- `POST /api/v1/import` applies a document in one transaction as upserts by natural key, reports
  `created`/`updated`/`skipped`/`error` per resource, writes nothing if any resource errors, and supports
  `dry_run=true`. Import never deletes.
- The bootstrap document schema grows what export needs and bootstrap lacks today (membership enable flags, per-bundle
  tool curation, secret placeholders); every existing bootstrap document stays valid.
- Admin UI: an export button and an import with a dry-run preview before applying.
- Users, OAuth server state, API key values, audit records and upstream OAuth tokens are never exported.

Out of scope (carried from the original spec): cross-version migration of export documents beyond `version`-field
gating — the importer supports the current version; older versions are best-effort.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `management`: adds MGMT-17..MGMT-22 — the export document, secret placeholders, transactional additive import with
  dry run, and the UI.
- `security`: adds SEC-11, the controls on a secret-bearing export.
- `operations`: adds OPS-18, management events in the audit log.
- `bundles`: BND-32 — export/import carries a bundle's prompts and resources, and import deletes none.
- `bundles`: BND-10 — the bundle name is the natural key for export and import as well as bootstrap, and a rename
  action that warns about it.
- `upstreams`: UPS-16 — the export document uses the key `upstreams` too.

## Impact

- Code: a new export/import use case in `application/` built on the bootstrap document and the management services; a
  controller under `api/management/controllers/`; schema additions in `application/bootstrap/` and
  `application/schemas/`; the admin UI (bundles page or settings).
- API: two new routes and their DTOs; `cd apps/web && npm run openapi` regenerates the client.
- Bootstrap: accepts the extended document (additions are optional, so existing files keep working). Coordinate with
  `add-bootstrap-api-keys`, which also extends the document, but API keys stay out of the export (MGMT-21).
- Docs: a new page under `docs/manage/` or `docs/self-hosting/`, and `docs/self-hosting/operations.md`, which today
  says there is no export or import.
- ADR: one new ADR (next free number) recording that export and bootstrap share one document schema with secret
  placeholders.

## Decisions

- **BND-10 — bundles get a rename action.** `POST /api/v1/bundles/{name}:rename?new_name=&force=` renames a bundle, its
  endpoints and curation following by id. Because bootstrap and import key bundles by name, a document still naming
  the old name would create a new bundle: the rename is refused with `409` explaining that unless `force=true`
  acknowledges it, like an upstream rename (UPS-5). The bundle page offers it with that acknowledgement.
- **SEC-11 — a management-event kind in the audit log.** An audit record gains a `kind` (`tool_call` or `management`)
  and an `action`; a secret-bearing export writes a `management` record with action `export.secrets_included`, the
  admin's user id and the time (OPS-18). The audit list filters by kind, and the CSV export carries both columns.
