# Tasks

## 1. Cancellation

- [ ] 1.1 Register each in-flight modern call under a key derived from the caller's identity subject, the endpoint and
  the request id, and publish a modern `notifications/cancelled` under the same derivation; verify with api tests citing
  PROT-3 that a cancel from the same caller ends the call (also across two app instances) and a cancel from another
  caller does not
- [ ] 1.2 Watch for client disconnect while a buffered handshake-era call runs and cancel it through its call handle;
  verify with an api test citing PROT-3 that the upstream call ends and `post_call` receives outcome `cancelled`

## 2. Capability advertisement

- [ ] 2.1 Make bundle capability aggregation take whether member list changes and resource updates are delivered, and
  pass "not delivered" until upstream session pooling provides delivery; verify with domain tests citing PROT-11 for
  both settings (own resources keep `listChanged`, member-only resources lose `listChanged` and `subscribe`)
- [ ] 2.2 Verify with an api test citing PROT-11 that `initialize` and `server/discover` on a bundle whose member
  advertises `resources.subscribe` no longer advertise `subscribe`

## 3. Cache hints

- [ ] 3.1 Mark a `tools/list` result that contains a `__connect_account` tool `cacheScope: "private"`; verify with an
  api test citing PROT-16 for a caller without a connection (private) and one with it (public)

## 4. Conformance suite

- [ ] 4.1 Add a harness under `tests/conformance/` that runs the MCP conformance suite (the MCP project's published
  server conformance runner) against the compose stack's `demo` endpoint for one revision given as a parameter; verify
  it passes locally for every served revision
- [ ] 4.2 Add a CI job in `.github/workflows/ci.yml` that brings up the compose stack and runs the harness once per
  served revision (matrix read from the gateway's supported-versions list); verify the job runs green on the PR
- [ ] 4.3 Document the harness in `CONTRIBUTING.md` (how to run it, where adding a revision plugs in) and verify
  `uv run rumdl check .` passes

## 5. Documentation

- [ ] 5.1 Update the docs pages that describe cancellation, resource subscriptions and cache scopes, and remove the
  advertised-but-undelivered entry from `docs/arc42/11-risks-and-technical-debt.md`; verify
  `python3 tools/check_docs_links.py` passes

## 6. Gates

- [ ] 6.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .` and `uv run lint-imports` and verify
  all pass
- [ ] 6.2 Run `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py` and
  `check_adr_graph.py` and verify all pass
- [ ] 6.3 Run `cd apps/web && npm run openapi` if a DTO or route changed and verify the generated files are otherwise
  unchanged
- [ ] 6.4 Run `openspec validate --all --strict` and verify it passes
