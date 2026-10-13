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
  dry run, and the UI. On archive, extend the slice's Purpose to mention export and import.
- `security`: adds SEC-11, the controls on a secret-bearing export.
- `bundles`: BND-32 — export/import carries a bundle's prompts and resources, and import deletes none.
- `bundles`: BND-10 — the bundle name is the natural key for export and import as well as bootstrap.
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

## Open decision

- **BND-10 rename warning.** The original BND-10 said the UI/API MUST warn on a bundle rename that automation keyed on
  the old name will see a new bundle. No bundle rename exists (upstreams have `:rename` with `force`, UPS-5). The delta
  as written keeps "no rename" and drops the warning. The alternative is to add a bundle rename action with the same
  `force` acknowledgement and warning; if the maintainers choose it, add that action and a scenario to the BND-10 delta
  and a task group before applying.
- **What "audit-logged" means for SEC-11.** The audit log holds one record per tool call (OPS-1); a management action
  has no record kind there. Either add a management-event kind to the audit log, or settle for a WARN log line
  (`export.secrets_included`) naming the admin. The design proposes the log line; decide before applying.
