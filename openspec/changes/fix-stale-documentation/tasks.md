# Tasks

## 1. Operator-facing docs

- [ ] 1.1 In `docs/self-hosting/deploy.md`, replace "Redirects are not followed, so there is no per-hop gap" with an
  accurate statement (the MCP client follows redirects and the egress check is not repeated per hop) and verify
  against `infrastructure/egress/` and the FastMCP transport that the sentence matches the code
- [ ] 1.2 In the same file, state that the admin session cookie is host-only (no `Domain`) and that only `Secure`
  follows the public URL's scheme; verify against `api/oauth/controllers/login_controller.py`
- [ ] 1.3 Fix `README.md` quickstart step 2 (default seed: `echo` and `oauth-demo`; fleet in `deploy/seed.fleet.yaml`)
  and verify against `deploy/seed.yaml`
- [ ] 1.4 Fix `docs/manage/audit.md` (UI filters are time range, endpoint, tool, status; rejections go to logs; list is
  newest first) and verify against `apps/web/app/pages/audit.vue` and `AuditService`
- [ ] 1.5 Add a note to `docs/self-hosting/bootstrap.md` that API keys in the bootstrap document are not supported yet
  and `BUNDLEMCP_INITIAL_SERVICE_KEY` is the way to provision a first key; leave ADR-0013 unchanged; verify
  `python3 tools/check_docs_links.py`

## 2. Architecture docs

- [ ] 2.1 In `docs/arc42/11-risks-and-technical-debt.md`, remove "Inspector covers tools only" and correct the
  upstream `list_changed` / push sentence to "not delivered" (between or within calls); verify against
  `api/mcp/` that no upstream notification is forwarded
- [ ] 2.2 Rewrite `packages/bundlemcp/bundlemcp/api/mcp/README.md`: replace every deleted module name with the current
  module, drop `_drive_upstream`, and state that the session TTL is a fixed 24 h with `session_lifetime` registered but
  unused; verify `python3 tools/check_docs_symbols.py` and that `grep -E "composition\.py|streams\.py|signals\.py|
  metering\.py|upstream\.py|_drive_upstream"` finds nothing in it

## 3. Docstrings and field descriptions

- [ ] 3.1 Correct the module and function docstrings of `infrastructure/config/structured_logging.py` to stderr and
  verify by reading `logging.StreamHandler()`'s default stream
- [ ] 3.2 Remove the `/metrics` export claim from `infrastructure/inprocess/counters.py` and the "exported as a metric
  (OPS-9)" comment from `infrastructure/postgres/audit_writer.py`; verify `uv run ruff check .`
- [ ] 3.3 Correct `UpstreamBinding.identity_key`'s description to what is stored (the caller's `sub`, not yet read) and
  verify `uv run pytest -q packages/bundlemcp/tests/domain` passes (the model is not a DTO, so OpenAPI is unaffected)

## 4. Gates

- [ ] 4.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports` and verify all
  pass
- [ ] 4.2 Run `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py`,
  `check_adr_graph.py` and verify all pass
- [ ] 4.3 Run `openspec validate --all --strict` and verify it passes
