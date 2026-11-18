# Proposal

## Why

Nothing in CI fails a pull request on a known vulnerability, a committed secret or an insecure pattern in the code.
Dependabot proposes updates, but a vulnerable version can sit in the lockfiles until someone runs an audit by hand,
which is how finding M4 (fixed by `upgrade-vulnerable-dependencies`) came about. Three weaker spots sit beside it:

- **A stale `uv.lock` passes.** Every CI job runs `uv sync --all-packages` without `--locked`
  (`ci.yml`: backend, frontend, integration, conformance-revisions, conformance; `restore-rehearsal.yml`), and the
  gateway image installs with `uv sync --frozen`. A `pyproject.toml` change without a re-lock is tested against a
  re-resolved environment in CI and shipped against the old lock in the image.
- **Images move under the same tag.** No `FROM` line names a digest (`python:3.15.1-slim-bookworm`, `node:26-alpine`,
  `ghcr.io/astral-sh/uv:0.13.5`), and the compose stack pulls `chrislusf/seaweedfs:latest`,
  `cloudflare/cloudflared:latest` and `ngrok/ngrok:latest`. A rebuilt image can differ from the one CI tested, and
  nothing records which bytes were used.
- **Two package managers for one docs site.** The root `pnpm-lock.yaml` has an empty importer (`.: {}`), the root
  scripts run `pnpm --dir docs`, while `docs/` carries a `package-lock.json` and CI, `publish-docs.yml` and Dependabot
  all use npm. A developer following the README installs the docs with a different tool, and without the lockfile CI
  uses.

The 2026-10-29 code audit records these as findings S4, S5, S6 and S28.

## What Changes

- **A `security` job in CI** (DEP-14, added; DEP-10, modified), required by `ci-passed`:
  - audits the locked Python dependencies (the whole workspace lock, dev tools included) against the public advisory
    database and fails on any reported vulnerability;
  - audits the npm lockfiles of `apps/web` and `docs` (dev dependencies included) and fails on any advisory of
    moderate severity or above. The one advisory reported today, the low-severity `deepmerge` advisory
    (GHSA-gcqx-w48m-w2h4, build-time via nitropack, no patched release), stays below the bar;
  - scans the commits a pull request adds (and the commits a push to `main` adds) for secrets;
  - lints every Dockerfile.
- **Accepted advisories in one reviewed list.** An advisory that cannot be fixed yet is listed in
  `tools/advisory_allowlist.toml` with its reason and an expiry at most 90 days out. An expired entry fails the gate,
  so an exception is re-decided rather than forgotten.
- **Static security analysis of the Python code** (DEP-14): ruff's `S` (flake8-bandit) rules join the existing
  `select`, so the `Ruff` step and `uv run ruff check .` enforce them locally and in CI. The 57 findings outside the
  tests are fixed or, where they are false positives, suppressed line by line; the test suites and the release tools get
  narrow per-file ignores.
- **The lockfile is checked, not re-resolved** (DEP-10): every `uv sync` in CI uses `--locked`, and the gateway
  image's builder uses `--locked` instead of `--frozen`, so a lock that no longer matches `pyproject.toml` fails.
- **Images pinned by digest** (DEP-15, added):
  - every `FROM` in the five Dockerfiles, and the uv image the gateway builder copies from, names its tag and a
    `@sha256:` digest. The uv image becomes a named build stage, so Dependabot can see it;
  - every third-party image in `deploy/docker-compose*.yml` does too, and the three `:latest` tags become versioned
    tags. The private fleet images chosen through `${…_IMAGE}` variables are the one
    exception;
  - Dependabot keeps them current: its `docker` ecosystem also covers `examples/conformance-mcp` (missing today), and
    a `docker-compose` ecosystem is added for `deploy/`. Postgres and Valkey major versions are left to an operator,
    because they change the on-disk format;
  - a hermetic test fails on an unpinned reference. The ARC-2 version test keeps matching, since the tag stays in
    front of the digest.
- **One package manager for the docs** (no requirement change): `pnpm-lock.yaml` is deleted, and the root scripts
  become `npm --prefix docs …`, so `npm run docs:install` runs the same `npm ci` CI runs. The README and
  `docs/README.md` change with them.
- **Shorter Dependabot titles** (no requirement change): Dependabot's commit-message prefix becomes plain `chore`, and
  its groups get short names. A grouped update's title, such as
  `chore: Bump the npm group across 2 directories with 12 updates`, then fits the 72-character limit that the
  DEP-12 title check enforces; today the grouped titles are 77 to 81 characters and every one fails the check. A
  group holding a single update still gets Dependabot's long form (`… from 1.2.140 to 1.2.141 in /apps/web in the npm
  group across 1 directory`), which no configuration shortens; it is still retitled by hand (see design, Open
  Questions).
- **Non-root by number** (no requirement change): the gateway and web images switch to a numeric `USER` (`10001`,
  `1000`), which hadolint asks for (DL3066) and which a Kubernetes `runAsNonRoot` check needs.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `deployment`: DEP-10 (modified: the security job and the lockfile check join the gates), DEP-14 (added: the
  supply-chain security gate), DEP-15 (added: images are pinned by digest and kept current).

## Impact

- **Resolves:** audit findings S4, S5, S6 and S28 (2026-10-29). No GitHub issue.
- **Files:**
  - `.github/workflows/ci.yml` (the `security` job, `ci-passed.needs`, `--locked`) and
    `.github/workflows/restore-rehearsal.yml` (`--locked`)
  - `.github/dependabot.yml` (the `chore` prefix, short group names, `examples/conformance-mcp`, the `docker-compose`
    ecosystem, no Postgres or Valkey majors)
  - `tools/check_advisories.py` and `tools/advisory_allowlist.toml` (new), `.gitleaksignore` and `.hadolint.yaml`
    (new)
  - `pyproject.toml` (ruff `S` with per-file ignores; `pip-audit` as a dev dependency) and `uv.lock`
  - the library modules with a ruff `S` finding (the 18 `assert` statements, the token-name constants, the retry
    jitter)
  - `apps/gateway/Dockerfile`, `apps/web/Dockerfile`, `examples/{echo-mcp,conformance-mcp,oauth-demo-mcp}/Dockerfile`,
    `deploy/docker-compose.yml`, `deploy/docker-compose.replicas.yml`
  - `package.json`, `pnpm-lock.yaml` (deleted), `README.md`, `docs/README.md`
  - tests: `packages/bundlemcp/tests/infrastructure/test_check_advisories.py` and `test_image_pins.py` (new)
- **Contributors:** a pull request that adds a dependency with a known advisory, commits something that looks like a
  credential, or adds an unpinned image now fails CI with a message that names the fix. `uv sync --locked` failing in
  CI means "run `uv lock` and commit it".
- **Docs:** `CONTRIBUTING.md` (the gates, the allow-list, `uv lock`), `docs/arc42/07-deployment-view.md` (the CI-gates
  row). CI writes the CHANGELOG entry (DEP-12). No ADR: this adds CI gates and pins, it does not change the
  architecture, as with `release-from-every-pull-request`.
- **Not covered:**
  - static analysis of the TypeScript in `apps/web` (see design, Non-Goals);
  - a scheduled re-audit of `main`. Dependabot security updates, enabled in the repository settings, already open a
    pull request when a new advisory hits a locked version.
