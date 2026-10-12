# 42 — Config export / import

**Status:** Accepted · **Origin:** metamcp carry-over **Prior art:**
`../metamcp/apps/frontend/app/[locale]/(sidebar)/mcp-servers/export-import-buttons.tsx`

## Summary

One-file JSON export/import of the gateway's configuration (servers, bundles with curation, endpoints) for backup,
migration between instances, and seeding bootstrap files.

## Requirements

- **EXP-1** `GET /api/v1/export` returns a versioned JSON document
  (`{"version": 1, "upstreams": [...], "bundles": [...], "endpoints": [...]}`, keys per
  [SRV-16](10-server-registry.md)) containing all configuration by natural
  keys — the same Pydantic schema bootstrap consumes ([BOOT-1](41-bootstrap.md)).
- **EXP-2** Secrets (static header values, upstream OAuth client secrets) are **excluded** by default, exported as named
  placeholders (`{"$secret": "HEADER_NAME"}`); an explicit `?include_secrets=true` exports values for full backups under
  the controls of [SEC-11](70-security.md) (admin session only, audit-logged, warning field).
- **EXP-3** `POST /api/v1/import` accepts the deprecated `servers` key like bootstrap does
  ([BOOT-8](41-bootstrap.md)) and applies a document transactionally as upserts by natural key, reporting per-resource
  results (created/updated/skipped/error). `dry_run=true` validates and reports without writing.
- **EXP-4** Import never deletes resources absent from the document (additive/updating only); a `prune=true` flag MAY be
  added later — not v1.
- **EXP-5** Not exported: users, OAuth server state (clients/tokens), API key values, audit records, upstream OAuth
  tokens. These are identity/runtime state, not configuration.
- **EXP-6** UI: export button (bundles page or settings) and import with dry-run preview.

## Out of scope

- Cross-version migration of export documents beyond `version`-field gating (importer supports current version; older
  versions best-effort).

## Open questions

- None.
