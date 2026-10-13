# Design

## Context

See proposal.md for motivation. What exists today:

- `BootstrapDocument` (`application/bootstrap/bootstrap_document.py`) is a Pydantic model with `extra="forbid"`,
  `version` pinned to 1 and the lists `upstreams` (`BootstrapServer` = `ServerUpsert` + optional `upstream_oauth`),
  `bundles` (`BootstrapBundle` = `BundleUpsert` + member names + prompts + resources) and `endpoints`
  (`EndpointUpsert`). `BootstrapRunner.apply` drives the management services inside one unit of work and starts
  discovery probes only after commit (`ProbesAfterCommit`).
- What bootstrap cannot express: a membership's `enabled` flag (members are bare names, always enabled), per-bundle
  tool curation (`BundleTool`, keyed by tool **id**), and a secret that is withheld. `static_headers` is
  `dict[str, str]`; an empty dict on update keeps the stored headers, a non-empty one replaces them all.
- Static header values are stored as plain JSON on the server row; upstream OAuth client secrets are ciphertext under
  the token cipher (`SecretCipher`, absent when no encryption keys are configured).
- `ManagementAuth` resolves a `Principal` of kind `ADMIN` (session) or `SERVICE` (service API key).
- The audit log holds tool-call records only (OPS-1).

## Goals / Non-Goals

**Goals:**

- One schema for bootstrap and export, so an export is a bootstrap file and a bootstrap file is importable.
- Import reuses the management services, so every invariant (BND-14 override uniqueness, per-user upstream policy, BND-5
  once it lands, endpoint auth/profile rules) holds exactly as through the API.
- Placeholders round-trip: export → import on the same instance is a no-op.

**Non-Goals:**

- Pruning (`prune=true`), cross-version migration, partial imports that commit the good half.
- Exporting discovered tool definitions: the tool cache is rediscovered from the upstream, not configuration.

## Decisions

### D1. Extend the bootstrap document instead of a separate export schema

The export model *is* `BootstrapDocument`, extended compatibly:

- `BootstrapBundle.upstreams` accepts either a name (today's form, meaning enabled with no curation) or an object
  `{name, enabled, tools: [{tool, enabled, override_name, override_title, override_description,
  override_annotations}]}`, where `tool` is the upstream tool name. The export always writes the object form.
- `ServerUpsert.static_headers` and `UpstreamOAuthConfig.client_secret` accept a `SecretRef` (`{"$secret": NAME}`)
  besides a string. The DTO used by the regular API keeps `str` only; the union lives on the bootstrap subclasses, so
  `PUT /api/v1/upstreams/{name}` does not start accepting placeholders.

*Alternative:* a dedicated `ExportDocument`. Rejected: two schemas drift, and MGMT-17 requires the bootstrap schema.

Layer: `application/bootstrap/` (models), `domain/` untouched.

### D2. Curation is keyed by (upstream name, tool name)

`BundleTool` references a tool row id, which differs per instance and does not exist until discovery ran. Export
writes the upstream tool name; import resolves it to the target's tool row. A curation entry whose tool is not in the
target's cache yet is reported `skipped` with the reason "tool not discovered yet; re-import after discovery" and does
not fail the document. Re-importing after discovery completes it, which is safe because import is idempotent.

*Alternatives:* run discovery synchronously during import (blocks on upstreams, contradicts "never blocks on probing"
in UPS-2); create placeholder tool rows (pollutes the cache with tools that may never exist). Both rejected.

### D3. Placeholders resolve to "keep what is stored"

On import, a `SecretRef` for a header means: keep the target's stored value of that header. Because a non-empty
`static_headers` replaces all headers, the import use case merges: literal values from the document, stored values for
placeholders. A placeholder with no stored value is an `error` for that upstream (MGMT-18). An OAuth client secret
placeholder works the same way through the upstream OAuth client service.

### D4. One use case, one transaction, results collected per resource

`ConfigImportService` (`application/management/`) opens one unit of work, applies upstreams, bundles (members,
curation, resources before prompts), then endpoints, catching each resource's service error into an
`ImportResult(kind, name, outcome, message)`. Outcome `skipped` is decided by comparing the stored read model with the
one the upsert would produce. If any result is `error`, or `dry_run` is set, the transaction is rolled back; probes are
released only after a real commit. `BootstrapRunner.apply` delegates to the same use case and raises on any error, so
bootstrap and import cannot diverge.

`ConfigExportService` (`application/management/`) reads through the repositories and builds the document; with
secrets, it decrypts client secrets through `SecretCipher` (no cipher configured → no client secrets to export).

### D5. Routes and secret controls

`ConfigTransferController` under `api/management/controllers/` (a `ManagementController`, so authentication is
inherited): `GET /export` with `include_secrets`, `POST /import` with `dry_run`, body = the document. The handler
refuses `include_secrets=true` with `403` unless the `Principal` is `ADMIN` (SEC-11) and passes the principal to the
service, which writes the record and sets `warning`.

The SEC-11 record is a WARN structured log line `export.secrets_included` with the admin user id (never values), as
the audit log has no management-event kind. This is the proposal's open decision; if a management-event audit kind is
chosen instead, it lands in this change with its own task.

### D6. UI

An *Export* button and an *Import* dialog on the settings page: the file is read in the browser, posted with
`dry_run=true`, the per-resource report is shown, and *Apply* posts it again without `dry_run`. Types come from the
generated OpenAPI client.

## Risks / Trade-offs

- [A secret-bearing export file leaks] → admin session only, `warning` field, docs say to treat it as a credential;
  the default is placeholders.
- [Large documents (4 MiB of resources per bundle) exceed the request size limit] → `/api/v1` has no body limit today;
  if `harden-http-edge` adds one, import may need a higher limit for this route — revisit then.
- [Curation silently incomplete after import to a fresh instance] → `skipped` results name each tool and the reason;
  docs say to re-import after discovery.
- [Bootstrap behaviour changes through the shared use case] → bootstrap tests stay green and keep their strict-mode
  semantics; the document additions are optional.

## Migration Plan

No data migration. Existing bootstrap files remain valid. Rollback is removing the routes; the schema additions are
backwards compatible.
