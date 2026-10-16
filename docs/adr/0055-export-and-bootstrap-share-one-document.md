# ADR-0055: Export, import and bootstrap share one document, with secrets as placeholders

**Status:** accepted · **Date:** 2026-10-16

## Context

Operators had no way to take a gateway's configuration out or move it to another instance; the documentation sent
them to hand-written bootstrap files. Bootstrap already applied a declarative document through the management
services in one transaction, but could not express a membership's enable flag, per-bundle tool curation or a secret
that is withheld, and nothing wrote such a document.

## Decision drivers

- An export must be usable as a bootstrap file unchanged, and a bootstrap file importable.
- Every invariant the management API enforces holds for an import too.
- An export is safe to hand around by default: no credential leaves the gateway unless a person asks for it.
- Export then import on the same instance changes nothing.

## Decision

- **One schema.** The export is a `BootstrapDocument`, extended compatibly: a bundle member may be an object with its
  enable flag and its tools' curation, and a header value or client secret may be a placeholder
  `{"$secret": "<name>"}`. The management API's own DTOs keep plain strings, so only documents accept placeholders.
- **Curation by tool name.** Curation names the tool as its upstream does, since tool ids differ per instance and
  exist only after discovery. A tool not discovered yet is skipped, not failed; importing again after discovery
  completes the curation.
- **A placeholder keeps what is stored.** With nothing stored under that name the resource errors.
- **One import path.** `ConfigImportService` applies a document resource by resource through the management services
  in one unit of work and reports each as created, updated, skipped or error; any error, or a dry run, rolls the
  whole transaction back, and servers are probed only after a real commit. Bootstrap runs the same code, failing on
  the first error as before. Import never deletes.
- **Secrets on request, by a person, on the record.** `include_secrets=true` is refused for service keys, adds a
  `warning` field, and writes an audit record of the new `management` kind with action `export.secrets_included`.
- **Bundles can be renamed, loudly.** Because documents key bundles by name, a rename is an explicit action that
  refuses with `409` unless `force=true` acknowledges that a document still naming the old bundle creates a new one.

## Alternatives considered

- **A dedicated export schema.** Two schemas drift; the export would stop being a bootstrap file.
- **Discover synchronously during import** so curation always resolves. It blocks on upstreams that may be down.
- **Commit the resources that succeed.** A half-applied document is harder to reason about than a refused one.
- **A WARN log line for a secret-bearing export.** Logs are not a durable trail; the audit log is.

## Consequences

### Positive

- Backups, staging-to-production moves and first bootstrap files come from one route.
- Bootstrap and import cannot diverge: they are one implementation.

### Trade-offs

- Curation on a fresh target needs a second import after discovery.
- A large document can exceed the request size limit; the docs say to raise it or import bundle by bundle.
- A notification stream opened before a bundle rename keeps the old name until the client reconnects.
