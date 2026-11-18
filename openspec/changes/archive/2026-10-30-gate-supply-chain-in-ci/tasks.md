# Tasks

## 1. Static security analysis of the Python code (DEP-14)

- [x] 1.1 Add `"S"` to `[tool.ruff.lint] select` in `pyproject.toml`, with `[tool.ruff.lint.per-file-ignores]` for
      `packages/bundlemcp/tests/**` and `tests/**` (exactly the `S` rules `uv run ruff check . --select S` reports
      there: measured: `S101`, `S104`–`S107`, `S603` for the package tests; `S101`, `S105`, `S603`, `S607`, `S608` for
      `tests/**`), `tools/**` and `deploy/*.py` (`S603`, `S607`, `S310`) and `examples/**` (`S104`). Verify that no
      ignore pattern matches `packages/bundlemcp/bundlemcp/`
- [x] 1.2 Replace the 10 `assert` statements left in the library after #169 and #171 (the 9 modules
      `ruff check --select S101` lists outside the tests) with explicit checks that raise, in the same place. Verify
      with `uv run ruff check .` clean for `S101` and `uv run pytest -q` passing. After rebasing onto #176, its new
      `store_conflict_handler` got the same explicit check as `store_unavailable_handler`
- [x] 1.3 Put a line-level `# noqa: S105` / `S106` on the token-kind constants (`domain/shared/secrets.py`,
  `domain/oauth/grant_type.py`, `domain/oauth/token_endpoint_auth_method.py`, `domain/servers/server_auth_mode.py`,
  `domain/servers/forward_header_rules.py`, `infrastructure/valkey/delegated_token_store.py`,
  `application/management/config_export_service.py`, `application/oauth_server/introspection_service.py`,
  `examples/oauth-demo-mcp/serve.py`), `# noqa: S311` on the retry jitter in `infrastructure/postgres/audit_writer.py`,
  and `# noqa: S310` in `docs/brand/build_logo_text.py`. Verify with `uv run ruff check .` reporting nothing
- [x] 1.4 Add `test_dep14_ruff_security_rules_cover_the_library` in
  `packages/bundlemcp/tests/infrastructure/test_ci_gates.py`: `select` contains `"S"`, and no per-file ignore
  pattern matches a path under `packages/bundlemcp/bundlemcp/`. Verify it fails when `"S"` is removed from a copy of
  the configuration
- [x] 1.5 In `CONTRIBUTING.md`, say that `uv run ruff check .` includes the security rules, and that a false positive
  gets a line-level `noqa`, never a per-file ignore in the library. Verify with `uv run rumdl check .`

## 2. Install from the committed lock (DEP-10)

- [x] 2.1 Change every `uv sync --all-packages` in `.github/workflows/ci.yml` (`backend`, `frontend`, `integration`,
  `conformance-revisions`, `conformance`) and `.github/workflows/restore-rehearsal.yml` to
  `uv sync --locked --all-packages`. Verify locally: `uv sync --locked --all-packages` passes on the branch, and fails
  saying the lockfile needs updating after a dependency is added to a scratch copy of `pyproject.toml` without
  `uv lock`
- [x] 2.2 Change both `uv sync --frozen` calls in `apps/gateway/Dockerfile` to `--locked`. Verify with
  `docker build -f apps/gateway/Dockerfile .` succeeding, and failing at the first sync when `uv.lock` is stale
- [x] 2.3 Add `test_dep10_every_workflow_installs_from_the_lock` to `test_ci_gates.py`: every `uv sync` in
  `.github/workflows/*.yml` and every `uv sync` in a Dockerfile carries `--locked`. Verify it fails on a workflow text
  with a bare `uv sync --all-packages`
- [x] 2.4 In `CONTRIBUTING.md`, under development setup, say that CI installs with `--locked`, and that a failure there
  means running `uv lock` and committing `uv.lock`. Verify with `uv run rumdl check .`

## 3. Images pinned by digest (DEP-15)

- [x] 3.1 In `apps/gateway/Dockerfile`, add a stage `FROM ghcr.io/astral-sh/uv:0.13.5@sha256:<digest> AS uv` and copy
  from `uv`. Pin both `python:3.15.1-slim-bookworm` references, `node:26-alpine` (both stages of
  `apps/web/Dockerfile`) and the three `examples/*/Dockerfile` bases as `<tag>@sha256:<digest>`. Resolve each digest
  with `docker buildx imagetools inspect <image>:<tag>` (the multi-platform index digest). Verify that both images and
  the three examples build, and that `uv run pytest -q packages/bundlemcp/tests/infrastructure/test_runtime_versions.py`
  still passes
- [x] 3.2 Pin every third-party image in `deploy/docker-compose.yml` and `deploy/docker-compose.replicas.yml` the same
      way. `chrislusf/seaweedfs`, `cloudflare/cloudflared` and `ngrok/ngrok` move from `:latest` to their current
      versioned tags, and one fleet service moves from `node:20-alpine` to `node:24-alpine`. Leave the three
      `${…_IMAGE:-…}` fleet images as they are. Verify with
      `docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.replicas.yml config` succeeding,
      `python3 tools/check_compose_ports.py` passing, and every pinned reference pulling by its digest (the integration
      job is 9.1)
- [x] 3.3 Add `packages/bundlemcp/tests/infrastructure/test_image_pins.py`, line-based like
  `tools/check_compose_ports.py`. `test_dep15_every_image_is_pinned_by_digest` covers `FROM` (skipping stage aliases)
  and `COPY --from=<image>` in `apps/*/Dockerfile` and `examples/*/Dockerfile`, and `image:` in
  `deploy/docker-compose*.yml`, exempting only variable-chosen images of `fleet`-profile services.
  `test_dep15_the_check_catches_a_floating_tag` checks the detector on inline texts: `node:26-alpine` and
  `example/image:latest` are reported, an image with `@sha256:` is not, `FROM builder` is not, and
  `${FLEET_IMAGE:-ghcr.io/x/y:latest}` under a fleet service is not. Verify both pass on the repository and the first
  fails on a copy with one digest removed
- [x] 3.4 In `.github/dependabot.yml`: add `/examples/conformance-mcp` to the `docker` directories; add a
  `docker-compose` ecosystem for `/deploy` with the same weekly schedule, 7-day cooldown and `dependencies` label;
  and ignore `version-update:semver-major` for `postgres` and `valkey/valkey` there. Verify with
  `uvx check-jsonschema --builtin-schema vendor.dependabot .github/dependabot.yml` (GitHub's own validation and the
  first Dependabot run are 9.2)
- [x] 3.5 In `.github/dependabot.yml`, set `commit-message: {prefix: "chore"}` on every ecosystem, and rename the groups
      to `actions`, `npm`, `uv`, `images` and `compose`. Keep the `python-images` group's comment and patterns, with the
      group renamed to `images`. Verify with
      `uv run python tools/pull_request_release.py labels "chore: Bump the images group across 5 directories with 10 updates"`
      accepting the title
- [x] 3.6 In `CONTRIBUTING.md`, say that every image is pinned by tag and digest, that Dependabot moves both, and how
  to resolve a digest by hand (`docker buildx imagetools inspect`). `docs/self-hosting/deploy.md` already tells
  operators to pin bundlemcp's own images by version or digest and needs no change. Verify with
  `python3 tools/check_docs_links.py` and `uv run rumdl check .`

## 4. Dockerfile lint findings (DEP-14)

- [x] 4.1 Change `USER bundlemcp` to `USER 10001` in `apps/gateway/Dockerfile` and `USER node` to `USER 1000` in
  `apps/web/Dockerfile`. Verify with `docker run --rm --entrypoint id bundlemcp-gateway:ci` printing `uid=10001` (and
  `uid=1000` for the web image), and both images reaching `healthy` on an isolated network with Postgres and Valkey,
  the gateway applying `deploy/seed.yaml` (the integration suite is 9.1)
- [x] 4.2 Add an inline `# hadolint ignore=DL3008` above the `apt-get install` in
  `examples/oauth-demo-mcp/Dockerfile`, with a comment that says why. Add a root `.hadolint.yaml` with
  `failure-threshold: info`. Verify with `hadolint --config .hadolint.yaml` over all five Dockerfiles exiting 0

## 5. Dependency advisory checker (DEP-14)

- [x] 5.1 Add `pip-audit` to the root dev dependencies and run `uv lock`. Verify that `uv run pip-audit --version`
  runs on Python 3.15. If it does not, record that in the PR and use the `--python 3.13` fallback from the design
- [x] 5.2 Add `tools/check_advisories.py` (run as `uv run python tools/check_advisories.py`; see design,
  Implementation Notes) and an empty `tools/advisory_allowlist.toml` (one commented example entry
  showing `id`, `package`, `reason`, `expires`). The checker runs the `uv export … | pip-audit --format json` pipe and
  `npm audit --package-lock-only --json` in `apps/web` and `docs`. It counts every Python finding and npm findings of
  moderate severity or above; applies the allow-list; fails on an expired entry or one more than 90 days out; prints
  removable entries; tells a network failure apart from a finding; and exits non-zero with a message citing DEP-14.
  Verify with `uv run python tools/check_advisories.py` exiting 0 on the branch
- [x] 5.3 Add `packages/bundlemcp/tests/infrastructure/test_check_advisories.py` over recorded JSON fixtures, with test
      names that say what is checked: `test_dep14_python_finding_fails`, `test_dep14_moderate_npm_advisory_fails`,
      `test_dep14_low_npm_advisory_passes` (today's `deepmerge` chain from `apps/web`),
      `test_dep14_allowlisted_advisory_passes`, `test_dep14_expired_entry_fails`,
      `test_dep14_entry_beyond_90_days_fails` and `test_dep14_unmatched_entry_only_warns`. Verify that all pass with
      `uv run pytest -q`
- [x] 5.4 In `CONTRIBUTING.md`, describe the allow-list: when an entry is acceptable (no fixed release, a reason that
  says why the advisory does not reach bundlemcp), the 90-day limit, and removal once fixed. Verify with
  `uv run rumdl check .`

## 6. The `security` job (DEP-10, DEP-14)

- [x] 6.1 Add `.gitleaksignore` holding the fingerprints of the four example matches in the history
  (`docs/guide/authentication.md`, `docs/integrate/upstream-identity.md`, `tests/integration/test_key_rotation.py`,
  `packages/bundlemcp/tests/infrastructure/test_structured_logging.py`). Verify that
  `gitleaks git --redact --log-opts=HEAD .` over the full history of the branch exits 0
- [x] 6.2 Add the `security` job to `.github/workflows/ci.yml`: checkout with `fetch-depth: 0`, setup-uv (Python 3.15)
      and setup-node (24), both SHA-pinned like the other jobs; `python3 tools/check_advisories.py`; gitleaks as a
      release binary, version and SHA-256 checksum in the job's `env`, over `<base>..<head>` (the pull request's base,
      `github.event.before` on a push, the full history on `workflow_dispatch`); and the SHA-pinned
      `hadolint/hadolint-action` over the five Dockerfiles. Step names may cite DEP-14, comments may not. Verify with
      actionlint and the workflow schema, and by running the job's steps locally as written: the checker, the gitleaks
      install (checksum) and scan for a pull request, a push, a new branch and a manual run, and the action's own
      `hadolint.sh` in its pinned image (the job on the pull request is 9.3)
- [x] 6.3 Add `security` to `ci-passed.needs`. Add `test_dep10_ci_passed_requires_every_job` to `test_ci_gates.py`:
  every job in `ci.yml` other than `ci-passed` appears in its `needs`. Verify it fails on a copy with `security`
  removed from `needs`
- [x] 6.4 Demonstrate each failure once, locally rather than on a throwaway branch: pushing a fake AWS-shaped key to
  GitHub could raise secret-scanning alerts for the organisation and would leave the commit on GitHub. Verified locally
  with the job's own commands: a commit adding a generated AWS-shaped key fails the gitleaks step (2 findings, file
  and commit named, secret redacted); a Dockerfile with `FROM node:latest` fails hadolint (DL3007) and the pin test;
  an allow-list entry dated yesterday makes the checker exit 1
- [x] 6.5 Update the CI paragraph of `CONTRIBUTING.md` and the "CI gates" row of
  `docs/arc42/07-deployment-view.md` to list the security gate and the lockfile check. Verify with
  `python3 tools/check_docs_links.py`, `python3 tools/check_docs_symbols.py` and `uv run rumdl check .`

## 7. One package manager for the docs

- [x] 7.1 Delete `pnpm-lock.yaml`. Change the root `package.json` scripts to `npm --prefix docs ci` (`docs:install`)
  and `npm --prefix docs run dev|build|preview`. Verify with `npm run docs:install && npm run docs:build` from the root
  producing `docs/.vitepress/dist`, and with `git status` showing no new lockfile at the root
- [x] 7.2 Replace `pnpm docs:…` with `npm run docs:…` in `README.md` (lines 53 and 61) and `docs/README.md`
  (lines 12–14). Verify that `grep -rn pnpm --include=*.md --include=*.json . --exclude-dir=node_modules` finds
  only `apps/web/package-lock.json` (a dependency's own `engines` entry), and run `uv run rumdl check .`

## 8. Gates

- [x] 8.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`, the four
  `tools/check_*.py` documentation scripts, `python3 tools/check_compose_ports.py`,
  `uv run python tools/check_advisories.py`, `bash tests/deploy/test_stack_secrets.sh`,
  `python3 tools/check_spec_ids.py` and `openspec validate --all --strict`;
  all pass (no DTO or route changes, so no `npm run openapi`)

## 9. Verified in CI

These need GitHub and cannot be run before the pull request exists.

- [x] 9.1 The integration job is green with the pinned compose images and the numeric `USER` of both images (3.2, 4.1)
- [x] 9.2 GitHub's validation of `.github/dependabot.yml` reports no error on the pull request, and after merge the
  Dependabot view (Insights → Dependency graph → Dependabot) lists the `docker-compose` ecosystem with a successful
  run (3.4). Verified after merge: Dependabot ran
  `docker_compose in /deploy` successfully, and its `docker` run covers `/examples/conformance-mcp`
- [x] 9.3 The `security` job is green on the pull request (6.2). Verified on #175, CI run 41078767459, which also
  passed 9.1: integration 18 passed, browser suite 42 passed
