# Tasks

## 1. Python dependencies

- [x] 1.1 Read the fastmcp 4.1.x changelog for client-side changes (transports, pooling, `listen`), and note anything
  relevant in the PR description
- [x] 1.2 Raise `fastmcp>=4.1.2` in `packages/bundlemcp/pyproject.toml`, then run
      `uv lock --upgrade-package fastmcp --upgrade-package authlib --upgrade-package dnspython`
      and `uv sync --all-packages --locked`. Verify that
      `uv export --all-packages --no-hashes --no-emit-workspace | uvx pip-audit -r /dev/stdin --no-deps --disable-pip`
      reports no known vulnerabilities
- [x] 1.3 Raise the example upstreams' floor to `fastmcp>=4.1.2` in `examples/echo-mcp/Dockerfile` and
  `examples/conformance-mcp/Dockerfile`, and verify with `docker compose -f deploy/docker-compose.yml build echo-mcp`
- [x] 1.4 Verify with `uv run pytest -q`, the conformance harness for every served revision
  (`uv run python tests/conformance/run_conformance.py --revision <rev>` for each `--list-revisions` entry, with the
  compose `conformance` profile up) and the integration suite against the compose stack

## 2. Web and docs dependencies

- [x] 2.1 In `apps/web`, bump `nuxt` to the latest 4.6 patch and `@nuxt/ui` to `^4.12.0`, then run `npm install` and
  `npm audit fix` (without `--force`). Verify that `npm audit` reports no high or moderate vulnerability, and that
  `npm run openapi` shows no drift, `npm run typecheck` passes and `npm run build` succeeds. Known exception: the
  low-severity `deepmerge` prototype-poisoning advisory (GHSA-gcqx-w48m-w2h4), reached only at build time through
  nitropack's rollup plugin, has no patched release; `--force` would downgrade nuxt to 4.1, so it is left and named
  in the pull request
- [x] 2.2 In `docs/`, run `npm audit fix` (without `--force`). Verify that `npm audit --package-lock-only` reports 0
  vulnerabilities and that `npm run build` succeeds
- [x] 2.3 Name the closed advisories in the pull request description, from which CI writes the CHANGELOG entry
  (DEP-12)

## 3. Gates

- [x] 3.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`, the four
  `tools/check_*.py` scripts, `python3 tools/check_spec_ids.py` and `openspec validate --all --strict`; all pass
