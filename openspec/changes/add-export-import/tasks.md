# Tasks

## 1. Document schema

- [ ] 1.1 Add `SecretRef` (`{"$secret": NAME}`) and the bootstrap-only unions on `static_headers` and
  `client_secret` in `application/bootstrap/`; verify with tests that today's bootstrap fixtures still validate and
  that `PUT /api/v1/upstreams/{name}` still rejects a placeholder (MGMT-17, MGMT-18)
- [ ] 1.2 Let `BootstrapBundle.upstreams` accept a name or a membership object with `enabled` and `tools` curation keyed
  by upstream tool name; verify with schema tests for both forms and that unknown keys are still rejected (MGMT-17,
  MGMT-15)

## 2. Import use case

- [ ] 2.1 Implement `ConfigImportService` in `application/management/`: one unit of work, per-resource results
  (`created`/`updated`/`skipped`/`error`), rollback on any error or on `dry_run`, probes after commit only; verify
  with application tests on the memory fakes for each outcome, dry run, and one-error rollback (MGMT-19, MGMT-20)
- [ ] 2.2 Resolve placeholders to the stored secret and report a missing one as `error`; verify with tests for header
  and OAuth client secret placeholders (MGMT-18)
- [ ] 2.3 Resolve curation entries by (upstream, tool name), reporting undiscovered tools as `skipped` with the reason;
  verify with a test that a re-import after discovery applies the curation (MGMT-19)
- [ ] 2.4 Make `BootstrapRunner.apply` delegate to the import use case and fail on any `error`; verify the existing
  bootstrap tests pass unchanged and a test that a bootstrap document never deletes a prompt it omits (BND-32, MGMT-9)

## 3. Export use case

- [ ] 3.1 Implement `ConfigExportService` in `application/management/` producing a `BootstrapDocument` with placeholders
  by default and values with `include_secrets`; verify that export → import on the same instance reports every
  resource `skipped`, and that the export validates as a bootstrap document (MGMT-17, MGMT-18, UPS-16)
- [ ] 3.2 Verify with a test that users, OAuth clients/tokens/consents, API keys, audit records and upstream tokens are
  absent from an export with secrets (MGMT-21)

## 4. API

- [ ] 4.1 Add the export/import controller under `api/management/controllers/`, DTOs for the import report in
  `application/schemas/`, every field described, and register it in `main/app.py`; verify with API tests through the
  ASGI app (MGMT-17, MGMT-19, BND-10)
- [ ] 4.2 Refuse `include_secrets=true` for service keys with `403`, add the `warning` field and the
  `export.secrets_included` record (per the resolved open decision); verify with API tests for both principals and that
  no secret value appears in the log output (SEC-11, SEC-10)
- [ ] 4.3 Run `cd apps/web && npm run openapi` and verify `apps/web/openapi.json` and `apps/web/types/api.d.ts` are
  current

## 5. Admin UI

- [ ] 5.1 Add the export button and the import dialog with dry-run preview and confirm step; verify with a Playwright
  test citing MGMT-22 that nothing is written before confirmation, and `npm run typecheck` passes

## 6. Documentation

- [ ] 6.1 Document export and import (secret placeholders, `include_secrets` as a credential, re-import after
  discovery, no pruning) and update `docs/self-hosting/operations.md` and `docs/self-hosting/bootstrap.md`; verify
  `python3 tools/check_docs_links.py` and `check_docs_settings.py` pass
- [ ] 6.2 Add the ADR for the shared bootstrap/export schema with placeholders and link it from
  `docs/arc42/09-architecture-decisions.md`; verify `python3 tools/check_adr_graph.py` passes

## 7. Gates

- [ ] 7.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`, the four
  `tools/check_*.py` scripts, `cd apps/web && npm run openapi`, and `openspec validate --all --strict`; verify all pass
