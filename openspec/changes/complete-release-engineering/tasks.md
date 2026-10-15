# Tasks

## 1. Runtime versions (ARC-2)

- [ ] 1.1 Add `"engines": { "node": ">=24" }` to `apps/web/package.json` and an `.npmrc` with `engine-strict=true`;
  verify `npm ci` fails under Node 22 and passes under Node 24
- [ ] 1.2 Move the `docs` and `diagrams` jobs in `.github/workflows/ci.yml` and the job in `publish-docs.yml` to
  Node 24; verify the docs build and `npx likec4 validate docs/likec4` pass on Node 24 locally
- [ ] 1.3 Extend `packages/bundlemcp/tests/infrastructure/test_runtime_versions.py` (which already checks the Python
  versions, from adopt-python-3-14) with a test citing ARC-2 that fails on any `node-version` below 24 in
  `.github/workflows/*.yml`; verify it fails on a deliberately downgraded copy
- [ ] 1.4 Update `docs/self-hosting/requirements.md` and `CONTRIBUTING.md` with the versions; verify
  `uv run rumdl check .` passes

## 2. CI typecheck (DEP-10)

- [ ] 2.1 Add an `npm run typecheck` step to the `frontend` job before the build; verify it passes on `main` and that
  a deliberate type error fails the job
- [ ] 2.2 Update the CI list in `CONTRIBUTING.md` and `docs/arc42/` where the gates are enumerated; verify
  `python3 tools/check_docs_links.py` passes

## 3. Tagged releases (DEP-11)

- [ ] 3.1 Create `CHANGELOG.md` (Keep a Changelog layout, an *Unreleased* section and a line for the metering-hook
  protocol version per release) and a test or script that reads `METERING_PROTOCOL_VERSION` and checks the changelog
  names it; verify the check passes on the first entry
- [ ] 3.2 Extend `publish.yml` to run on `v*.*.*` tags and push both images as `:<version>`; verify with a pre-release
  tag on a fork or with `act` that the expected tags are produced
- [ ] 3.3 Add a release workflow that fails when the changelog has no entry for the tag, and otherwise creates the
  GitHub release from that entry, stating the metering-hook protocol version and whether it changed since the previous
  tag; verify on a test tag that the notes carry the version line
- [ ] 3.4 Document how a release is cut in `CONTRIBUTING.md`, how to pin a release in `docs/self-hosting/deploy.md`, and
  where protocol changes are announced in `docs/integrate/metering-hook.md`; verify the docs build passes

## 4. Restore rehearsal (DEP-8)

- [ ] 4.1 Script the documented rehearsal (`tools/` or `deploy/`): dump a seeded compose stack, restore into a scratch
  database, start a gateway on it with the same encryption keys, wait for `/readyz`, make one tool call; verify it
  passes locally against the compose stack and fails when the restore step is skipped
- [ ] 4.2 Run the script from a workflow on release tags and `workflow_dispatch`, gating the release workflow on it;
  verify a manual dispatch succeeds
- [ ] 4.3 Point the *Rehearsing the restore* section of `docs/self-hosting/deploy.md` at the script and the workflow;
  verify `python3 tools/check_docs_links.py` passes

## 5. Gates

- [ ] 5.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .` and `uv run lint-imports`; verify all
  pass
- [ ] 5.2 Run `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py` and
  `check_adr_graph.py`; verify all pass
- [ ] 5.3 Run `openspec validate --all --strict` and verify it passes (no DTO or route changes, so no
  `npm run openapi`)
