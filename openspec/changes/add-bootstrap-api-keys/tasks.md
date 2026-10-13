# Tasks

## 1. Decide before applying

- [ ] 1.1 Settle both open decisions in `proposal.md` (how a generated key reaches the operator; match by name or make
  key names unique) and edit `specs/management/spec.md` to match; verify
  `openspec validate add-bootstrap-api-keys --strict` passes

## 2. Document schema (MGMT-8, MGMT-10)

- [ ] 2.1 Add a `BootstrapApiKey` model in `application/bootstrap/` (`extra="forbid"`, every field described): name,
  kind, endpoint names, and exactly one of a variable reference or `create_if_missing`; add `api_keys` to
  `BootstrapDocument`; verify tests citing MGMT-8/MGMT-10 that an inline value, both sources at once, or neither are
  rejected
- [ ] 2.2 Resolve a variable reference at load time in `document_loader.py`, rejecting an unset variable or a value not
  in the `bmcp_sk_…` format with an error that names the variable but never echoes its value; verify tests citing
  MGMT-10 for both failures and a test that the error text holds no value

## 3. Applying keys (MGMT-10)

- [ ] 3.1 Give `ApiKeyService` a create-from-supplied-value path and a find-by-name query on the API-key repository
  contract (with its Postgres adapter and memory fake); verify repository tests on sqlite and the memory fake
- [ ] 3.2 Apply `api_keys` in `BootstrapRunner` after endpoints, inside the document's transaction, resolving scopes by
  endpoint name and skipping any key whose name exists; verify tests citing MGMT-10 for the reference, generated,
  existing-key and unknown-endpoint scenarios, and a MGMT-9 test that re-applying the document changes nothing
- [ ] 3.3 Deliver a generated value as the open decision settled (one-time log line, or an operator-named file) and make
      sure no other log line, audit record or error carries it; verify a test citing MGMT-10 that the value is announced
      once and not on the next start, and a SEC-10 test over the captured log output
- [ ] 3.4 Keep `ensure_initial_service_key` working unchanged next to the document's keys; verify the existing MGMT-10
  tests still pass

## 4. Documentation

- [ ] 4.1 Rewrite the *API keys* section of `docs/self-hosting/bootstrap.md` (document shape, variable references,
  generated keys, never-overwrite rule, the initial service key) and add any new setting to
  `docs/self-hosting/configuration.md`; verify `python3 tools/check_docs_settings.py` and the docs build pass
- [ ] 4.2 If the demo stack uses a bootstrap key, add it to `deploy/seed.yaml` and `deploy/.env.example`; verify the
  MGMT-13 test that the seed validates

## 5. Gates

- [ ] 5.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .` and `uv run lint-imports`; verify all
  pass
- [ ] 5.2 Run `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py` and
  `check_adr_graph.py`; verify all pass
- [ ] 5.3 Run `openspec validate --all --strict` and verify it passes (no DTO or route changes, so no
  `npm run openapi`)
