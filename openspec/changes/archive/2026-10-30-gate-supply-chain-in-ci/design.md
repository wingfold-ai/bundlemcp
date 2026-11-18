# Design

## Context

See [proposal.md](proposal.md). What exists today, read on 2026-10-29:

- **CI** (`.github/workflows/ci.yml`): jobs `backend`, `frontend`, `docs`, `diagrams`, `image`, `integration`,
  `conformance-revisions` and `conformance`, all listed in `ci-passed.needs`. Actions are pinned by commit SHA and kept
  current by Dependabot's `github-actions` ecosystem. Nothing audits dependencies, scans for secrets or lints
  Dockerfiles.
- **Repository:** `wingfold-ai/bundlemcp` is a private repository in an organisation. That rules out the free tiers of
  two obvious tools: CodeQL code scanning on a private repository needs GitHub Code Security, and `gitleaks-action`
  needs a licence key for an organisation account.
- **Today's findings**, so the gate starts green:
  - `pip-audit` over the workspace lock reports nothing.
  - `npm audit --package-lock-only` reports 7 low advisories in `apps/web`, all one chain: `deepmerge`
    (GHSA-gcqx-w48m-w2h4) via `@rollup/plugin-node-resolve` → `nitropack` → `nuxt`. It reports the same 7 with dev
    dependencies included, and 0 in `docs`. With `--audit-level=moderate`, both exit 0.
  - `gitleaks git` over all 486 commits finds 4 matches, all examples: two `curl-auth-user` in
    `docs/guide/authentication.md`, one in `docs/integrate/upstream-identity.md`, and one `generic-api-key` in
    `tests/integration/test_key_rotation.py`.
  - hadolint (default threshold `info`) finds DL3066 (non-numeric `USER`) in the gateway and web Dockerfiles, and
    DL3008 (unpinned `apt-get install git`) in `examples/oauth-demo-mcp/Dockerfile`. The other two are clean.
  - `ruff check --select S` finds 2,578 issues, 2,521 of them in the test suites (2,407 are `S101` `assert`). The 57
    outside the tests are listed under Decisions.
  - `uv lock --check` passes: the lock is current today.
- **Pins:** `docs/package.json` holds only `devDependencies`, so `--omit=dev` would audit nothing there. The ARC-2
  test (`packages/bundlemcp/tests/infrastructure/test_runtime_versions.py`) reads `\b(?:python:|uv:python)(\d+\.\d+)`
  from Dockerfiles and `^FROM\s+node:(\d+)` from the web Dockerfile. Dependabot's `docker` ecosystem covers
  `/apps/gateway`, `/apps/web`, `/examples/echo-mcp` and `/examples/oauth-demo-mcp`, but not
  `/examples/conformance-mcp`. The uv binary arrives through `COPY --from=ghcr.io/astral-sh/uv:0.13.5`. The
  `python-images` group lists `*astral-sh/uv`, but Dependabot has never opened an update for it.
- **Dependabot titles:** for a grouped update the title is `chore(deps): Bump the <group> group across <n>
  director(y|ies) with <m> updates` (77 to 81 characters with `minor-and-patch`). For a group of one update it is
  `… from <a> to <b> in <dir> in the <group> group across 1 directory` (97 to 127 characters). The DEP-12 check
  (`tools/pull_request_release.py`, `MAX_TITLE = 72`) fails all of them, so each pull request is retitled by hand
  (#165, #166).

## Goals / Non-Goals

**Goals:**

- A pull request cannot merge while it adds a dependency with a known advisory, a secret, an unpinned image or a
  Dockerfile lint finding, or while `uv.lock` disagrees with `pyproject.toml`.
- Every check runs locally with the same command CI runs.
- Every tool the gate uses has a pinned version that an automated update keeps current, wherever that is possible.

**Non-Goals:**

- Static analysis of the TypeScript in `apps/web`. The free options are CodeQL (not free here) and Semgrep's
  community rules (another tool and rule feed). The web app renders no HTML from untrusted strings outside Vue's
  escaping, and the gateway enforces every security decision. A later change can add it.
- Container image vulnerability scanning (Trivy, Grype). It reports OS-package CVEs that mostly have no fix in Debian
  bookworm, so it needs its own triage policy. Digest pins plus Dependabot keep the bases current.
- SBOM generation and image signing (provenance). Those are release-engineering concerns, not this gate.
- Re-auditing `main` on a schedule (see proposal, Not covered).

## Decisions

### One `security` job; the static analysis stays in the `Ruff` step

The new `security` job runs the dependency audit, the secret scan and the Dockerfile lint. It is listed in
`ci-passed.needs`. It needs no services and no `npm ci` (`npm audit --package-lock-only` reads the lockfile), so it
finishes in about a minute, in parallel with the rest.

The Python static analysis is ruff's `S` rule set (a re-implementation of flake8-bandit), added to
`[tool.ruff.lint] select`. It then runs wherever ruff already runs: the `backend` job's `Ruff` step, and
`uv run ruff check .`, which CLAUDE.md already makes a precondition for every change. A second ruff run in the
`security` job would add nothing.

Alternatives considered:

- **CodeQL.** Its data-flow analysis would be the strongest choice, and it covers TypeScript too. On this private
  organisation repository it needs GitHub Code Security, a paid add-on. It also takes several minutes per run, and
  its results land in the Security tab rather than in the job a contributor reads.
- **bandit.** It has the same rules as ruff `S`, but is a second tool and a second configuration, slower, and without
  ruff's per-file ignores and `noqa` handling.
- **Semgrep.** Broader rules, including for TypeScript, but the useful rule sets come from a registry the job would
  have to fetch, which is a moving input to a gate. It can be revisited together with TypeScript analysis.

### Ruff `S`: fix the library findings, scope the ignores

The 57 findings outside the test suites, by kind:

| Finding | Where | Resolution |
|---|---|---|
| `S101` `assert` (18) | 12 library modules, e.g. `api/mcp/tool_call/tool_call.py` (4), `config_import_service.py` (2) | Each becomes an explicit check that raises. An assertion vanishes under `python -O` / `PYTHONOPTIMIZE`, so an invariant guarded by it is not guarded |
| `S105`/`S106` (13) | Constant names that only name a token kind (`ACCESS_TOKEN_PREFIX`, `GrantType.REFRESH_TOKEN`, `CLIENT_SECRET_BASIC`, `DELEGATED_TOKEN_KEY`, …) and `examples/oauth-demo-mcp/serve.py` | `# noqa: S105` on each line; no value is a secret |
| `S311` (1) | Retry jitter in `infrastructure/postgres/audit_writer.py` | `# noqa: S311`; the jitter is not a security value |
| `S603`/`S607` (19) | `tools/*.py` and `deploy/rehearse_restore.py`, calling `git`, `gh`, `docker` with fixed argument lists | Per-file ignore for `tools/**` and `deploy/*.py` |
| `S310` (3) | `tools/changelog_writer.py` (a fixed `https` URL) and `docs/brand/build_logo_text.py` | Per-file ignore with the tools; the logo script gets a `noqa` |
| `S104` (3) | `examples/oauth-demo-mcp/serve.py` binds `0.0.0.0` inside its container | Per-file ignore for `examples/**` |

The test suites (`packages/bundlemcp/tests/**`, `tests/**`) ignore `S101`, the hard-coded-credential rules
`S105`–`S107` (fixtures are fake credentials), `S311`, `S603`/`S607` and `S608` (fixture SQL). The exact list is
whatever `ruff check --select S` reports there, and nothing broader. A per-file ignore never covers the library
package.

### The dependency audit goes through one checker with one allow-list

`tools/check_advisories.py` runs both audits and applies the allow-list:

- **Python:** `uv export --locked --all-packages --all-groups --all-extras --no-hashes --no-emit-workspace`, piped to
  `uv run pip-audit -r /dev/stdin --no-deps --disable-pip --format json` (the pipe the previous change used to verify
  M4). Python advisories mostly carry no severity, so any reported vulnerability counts.
- **npm:** `npm audit --package-lock-only --json` in `apps/web` and in `docs`. Advisories of `moderate`, `high` and
  `critical` severity count; `low` and `info` do not. Dev dependencies are included: they run in CI with a repository
  token and on every developer's machine, and M4's `vite` and `zod` advisories were exactly that case.
- **Allow-list:** `tools/advisory_allowlist.toml`, an array of entries with `id` (`GHSA-…`, `PYSEC-…` or `CVE-…`),
  `package`, `reason` and `expires` (a date). A counted finding whose id is listed is reported as accepted and does
  not fail. An entry past `expires` fails, and so does one more than 90 days out. An entry that matches nothing is
  printed as removable, but does not fail, so a fix landing upstream never turns an unrelated pull request red. The
  list starts empty: the `deepmerge` advisory is low and below the bar.

The checker exits non-zero with a message that names each package, version and advisory, and cites DEP-14. It is a
plain script beside the other `tools/check_*.py`, and the parsing and filtering are pure functions, tested
hermetically over recorded JSON (`test_check_advisories.py`).

`pip-audit` becomes a dev dependency in the root `pyproject.toml`. It is then locked in `uv.lock`, updated by
Dependabot's `uv` ecosystem, and audited by the same gate.

Alternatives considered:

- **`npm audit --audit-level=moderate` alone.** It passes today, but an unfixable moderate advisory would block every
  pull request with no way out except removing the gate. npm has no ignore option.
- **`audit-ci`.** It has an allow-list, but it is another npm tool to pin, and it handles only npm.
- **`uvx pip-audit@<version>`.** Dependabot cannot see a version written in a workflow, so it would go stale.
- **GitHub's dependency-review action.** Needs GitHub Code Security on a private repository.

### Secrets: gitleaks over the commits a run adds

The job checks out with `fetch-depth: 0` and runs `gitleaks git --redact --log-opts="<base>..<head>"`. On a pull
request, `<base>` is the pull request's base SHA. On a push to `main`, it is `github.event.before`. On
`workflow_dispatch`, the whole history is scanned.

The four example matches already in the history go into `.gitleaksignore` by fingerprint, so a full scan is also
clean. A future documentation example uses a `gitleaks:allow` comment on its line.

gitleaks runs as its release binary, version-pinned and verified against the release's published SHA-256 checksum.
`gitleaks-action` needs a licence key for an organisation account, and a `docker run` of its image is not something
Dependabot updates either.

### Dockerfile lint: the hadolint action

`hadolint/hadolint-action`, pinned by SHA like every other action, so Dependabot's `github-actions` ecosystem updates
it, runs over the five Dockerfiles with a root `.hadolint.yaml` at the default `failure-threshold: info`. The three
current findings are fixed rather than ignored where that is cheap:

- **DL3066:** `USER 10001` in the gateway (the `useradd --uid 10001` user) and `USER 1000` in the web image (the
  `node` user of the official image). Nothing changes at run time: the UID is the same. A numeric UID is also what
  Kubernetes' `runAsNonRoot` needs to verify a non-root user.
- **DL3008:** the `git` that `oauth-demo-mcp` installs and purges in the same layer gets an inline
  `# hadolint ignore=DL3008` with a comment explaining it. Pinning a Debian package version breaks the build as soon as
  bookworm's security archive drops that version, and this is a demo image.

### `--locked` everywhere, including the image

Every `uv sync --all-packages` in `ci.yml` (five jobs) and `restore-rehearsal.yml` becomes
`uv sync --locked --all-packages`. Both `uv sync` calls in the gateway builder switch from `--frozen` to `--locked`.
`--frozen` installs from the lock without checking it; `--locked` fails when the lock no longer matches the project.
At the first builder sync, the builder has the root `pyproject.toml`, `uv.lock` and the only workspace member's
`packages/bundlemcp/pyproject.toml`, which is everything uv needs to check the lock.

Alternatives considered:

- **`UV_LOCKED=1` in the workflow environment.** It does the same, but it is invisible at the call site and would also
  apply to the `uv run --no-project` tool calls in `ci-passed`. The flag on the command says what the step checks.
- **Leaving the image on `--frozen`.** CI's `--locked` proves the lock current for the same commit. But `--locked`
  costs nothing, and it also protects an image someone builds outside CI.

### Digest pins: tag and digest, kept current by Dependabot

Every reference becomes `<image>:<tag>@sha256:<digest>`. The tag stays, so a reader and the ARC-2 test still see the
version (`python:3.15.1-slim-bookworm@sha256:…` still matches `python:(\d+\.\d+)`), and Dependabot can still propose
the next tag. The digest makes a rebuild reproducible. Dependabot's `docker` and `docker-compose` ecosystems update
both together, and open a digest-only pull request when a tag is re-pushed (a Debian security rebuild of
`python:3.15.1-slim-bookworm`).

- **The uv image becomes a named stage:** `FROM ghcr.io/astral-sh/uv:0.13.5@sha256:… AS uv`, then
  `COPY --from=uv /uv /uvx /usr/local/bin/`. Dependabot reads `FROM` lines; nothing shows it reads `COPY --from`, and
  it has never proposed a uv update here. The stage is never run, so the build output does not change.
- **Compose:** `postgres:17-alpine`, `valkey/valkey:8-alpine`, `quay.io/keycloak/keycloak:26.4`, `caddy:2-alpine`,
  `caddy:2.10.2-alpine`, and the three `:latest` tags. Each `:latest` becomes the image's current versioned tag plus
  a digest. One fleet service runs `node:20-alpine`, which has been out of support since April 2026; it
  moves to `node:24-alpine`, the version CI uses, and is pinned rather than frozen on an unsupported runtime.
- **Exempt:** the three fleet services whose image comes from a `${…_IMAGE:-…}`
  variable. They are private first-party images, behind the `fleet` profile, that CI never pulls.
  An operator picks them through the variable, and Dependabot could not read their registry.
- **Dependabot:** add `/examples/conformance-mcp` to the `docker` directories. Add a `docker-compose` ecosystem for
  `/deploy`. Ignore `version-update:semver-major` for `postgres` and `valkey/valkey`, because a Postgres major needs a
  dump and restore (DEP-8), which is an operator's decision. Digest and minor updates still flow.
- **The test:** `packages/bundlemcp/tests/infrastructure/test_image_pins.py` reads every `FROM` line (with its stage
  aliases, so `FROM builder` and `COPY --from=builder` are not image references) and every `COPY --from=<image>` in
  `apps/*/Dockerfile` and `examples/*/Dockerfile`, and every `image:` in `deploy/docker-compose*.yml`. It fails on a
  reference without `@sha256:` that is not one of the exempt fleet services, naming the file, the line and the image.
  It is line-based, like `tools/check_compose_ports.py`, so it needs no YAML dependency.

Alternatives considered:

- **Exact tags without digests** (`python:3.15.1-slim-bookworm` already is one): the publisher re-pushes that tag for
  every Debian rebuild, so it pins nothing.
- **Digest only:** reproducible, but unreadable, and it breaks the ARC-2 test and Dependabot's tag updates.
- **Renovate:** it handles digests well too, but the repository already runs Dependabot for four ecosystems.

ARC-1 ("latest stable versions") is not in tension with this: it governs library version floors. A pinned image stays
current because Dependabot proposes every new tag and digest.

### npm for the docs; `pnpm-lock.yaml` goes

The root `package.json` has no dependencies, only four scripts that forward to `docs/`. `pnpm-lock.yaml` records
nothing (`importers: .: {}`), and everything that installs the docs (CI, `publish-docs.yml`, Dependabot's `npm`
ecosystem over `/docs`) uses npm and `docs/package-lock.json`. So the pnpm lock is deleted, and the scripts become:

- `docs:install`: `npm --prefix docs ci`, the install CI runs, from the committed lock;
- `docs:dev`, `docs:build`, `docs:preview`: `npm --prefix docs run <script>`.

`README.md` (lines 53 and 61) and `docs/README.md` (lines 12–14) change from `pnpm docs:…` to `npm run docs:…`.

Alternative considered: **switching to pnpm.** That means a pnpm lock for `docs` and `apps/web`, pnpm in CI caching, in
`apps/web/Dockerfile` and in `publish-docs.yml`, and a second package manager for contributors to install. All of that
cost buys nothing for two independent projects with no shared workspace.

### Dependabot titles: plain `chore` prefix and short group names

Each ecosystem gets `commit-message: {prefix: "chore"}` without `include: scope`, which turns `chore(deps):` and
`chore(deps-dev):` into `chore:`. The title check accepts a missing scope, and `chore` is `semver: none`, as now. The
groups are renamed:

| Ecosystem | Group, today | Group, new |
|---|---|---|
| `github-actions` | `actions` | `actions` |
| `npm` | `minor-and-patch` | `npm` |
| `uv` | `minor-and-patch` | `uv` |
| `docker` | `python-images` | `images` |
| `docker-compose` | — | `compose` |

The longest multi-update title is then `chore: Bump the images group across 5 directories with 10 updates`
(65 characters).

## Risks / Trade-offs

- [A new advisory is published against a locked version and turns every open pull request red on the same day] →
  this is the gate doing its job. The fix is a dependency bump, which Dependabot security updates usually open
  themselves. If there is no fix, an allow-list entry with a reason and an expiry unblocks the pull requests in one
  reviewed change.
- [The advisory databases are unreachable and the job fails for reasons unrelated to the change] → the checker tells a
  network failure apart from a finding and says so. A re-run is the remedy. No fallback passes the gate silently.
- [`pip-audit` does not yet support Python 3.15, or pulls a dependency that does not] → it reads requirement lines and
  queries an API, and does not install anything (`--disable-pip --no-deps`). If it does not run on 3.15, the checker
  runs it through `uv run --python 3.13 --with pip-audit`, still from the locked dev group's version.
- [Replacing 18 `assert`s changes behaviour] → each becomes an explicit check in the same place that raises an
  internal error, so it still fails the request exactly where the assertion did. No library code catches
  `AssertionError` today (a grep finds none), so no handler depends on the old type. The hermetic suite runs over
  those paths.
- [A Dependabot digest pull request for a re-pushed `python` tag lands often] → it is grouped with the other image
  updates, waits 7 days (`cooldown`), and the hermetic and image-build jobs prove it before merge.
- [A registry deletes an old digest and a pinned pull fails] → the failure is loud (the image job or `compose pull`
  names the reference), never a silent substitution. Dependabot normally moves the pin forward long before, and a
  manual bump is the fix otherwise.
- [gitleaks's version goes stale, because no automated update sees the binary pin] → the version and its checksum sit
  in one `env` block of the job, and a stale scanner still catches the classic patterns. See Open Questions.
- [Ruff `S` slows contributors with false positives] → today's 57 are resolved in this change. A new false positive
  gets a line-level `noqa`, which a reviewer sees in the diff.

## Migration Plan

One pull request. Order inside it: the ruff `S` fixes and ignores first (the backend job stays green), then `--locked`,
then the pins and the Dependabot configuration, then the `security` job and its `ci-passed.needs` entry last. The new
check is then green the first time it is required. The `ci-passed` ruleset needs no change, because it requires
`ci-passed` only. Rollback is reverting the pull request. No runtime behaviour, data or configuration changes.

## Open Questions

- **Single-update Dependabot titles.** A group that receives exactly one update still gets Dependabot's long form
  (`chore: Bump fastapi from 0.142.3 to 0.142.4 in the uv group across 1 directory`, 78 characters), and no
  `dependabot.yml` option shortens it. Removing the remaining manual retitle needs a DEP-12 change: either exempt
  `dependabot[bot]` from the length limit, or have `release-entry.yml` retitle bot pull requests. That is outside
  this change's requirements. Until then, those pull requests are retitled by hand, as now.
- **gitleaks updates.** If the organisation registers for a free `gitleaks-action` licence, the binary pin can become
  a SHA-pinned action that Dependabot updates. This does not change the gate.

## Implementation Notes

Measured again on 2026-10-29 on top of #167–#173, which changed several of the facts above. Where the implementation
differs from the Decisions, this is why.

- **Ruff `S`: 49 findings outside the tests, not 57.** #169 and #171 already removed eight of the library `assert`s.
  What remained: `S101` ×10 in 9 modules, `S105` ×10, `S106` ×3, `S311` ×1, `S310` ×3, `S603` ×10, `S607` ×9 and
  `S104` ×3. In the tests: `S101` ×2,751, `S106` ×75, `S105` ×33, `S603` ×21, `S607` ×5, and one each of `S104`,
  `S107` and `S608`; no `S311`. The per-file ignores list exactly the rules each pattern reports:
  `packages/bundlemcp/tests/**` gets `S101`, `S104`–`S107` and `S603`; `tests/**` gets `S101`, `S105`, `S603`, `S607`
  and `S608`.
- **Three `assert`s did not become a bare raise in place.** `ConfigImportService._oauth_client` now takes the
  already-checked client as a parameter, so there is nothing left to check. The member lookup in `_curate` raises
  `NotFoundError`, which the import already reports as a failed entry instead of crashing. `GuardedBackend` raises the
  same `HostUnresolvable` it raises for an empty resolution. The other seven raise `TypeError`, `RuntimeError` or
  `ApiKeyValueUnavailable` where the `assert` was.
- **The checker runs as `uv run python tools/check_advisories.py`**, not `python3`. Its findings, allow-list entries
  and verdict are Pydantic models, as every structured value in the repository is, and it runs pip-audit as
  `python -m pip_audit` from the same locked environment. pip-audit 2.10.1 runs on Python 3.15, so the `--python 3.13`
  fallback is not needed.
- **npm: a moderate advisory in `docs`.** `docs/package-lock.json` locked `vite` 6.4.4, which GHSA-8g5g-mxqh-grgj
  (moderate, `server.fs.deny` bypass, dev server only) affects. 6.4.5 fixes it, so `npm audit fix --package-lock-only`
  moved the lock to 6.4.5 (a patch release, nothing else changed); the docs site builds on it. No allow-list entry
  was needed, and the list starts empty. `apps/web` still reports only the seven low `deepmerge` entries, one
  advisory. The Vitest, `@nuxt/test-utils` and `happy-dom` dependencies from #173 add nothing.
- **gitleaks scans one history, not every ref.** `gitleaks git` reads `git log --all`, so locally it also reports
  commits of unmerged branches; the second `docs/guide/authentication.md` match was such a commit (the pre-squash
  commit of #45). The checked-out history holds 4 matches: the two `curl-auth-user` examples,
  `tests/integration/test_key_rotation.py`, and, new since the design, a fake token in
  `packages/bundlemcp/tests/infrastructure/test_structured_logging.py` (#168). `.gitleaksignore` lists those four. In
  CI the manual run scans the history of the checked-out commit (`--log-opts=<sha>`), not `--all`, so fingerprints
  of branch commits never need an entry. gitleaks is 8.30.1.
- **hadolint** runs as `hadolint/hadolint-action` v3.5.0, which ships hadolint 2.15.1. It still reported the three
  findings above, and nothing more.
- **Tags for the `:latest` images** are the versions `:latest` pointed at on 2026-10-29: `chrislusf/seaweedfs:4.50`,
  `cloudflare/cloudflared:2026.10.6` and `ngrok/ngrok:3.39.13-debian` (ngrok's `latest` is its Debian variant).
- **The `compose` Dependabot group** takes every update (`patterns: ["*"]`), as `actions` does.

- **Local verification, and what is left for CI.** Every pinned reference pulls by its digest. Both images reach
  `healthy` on an isolated network with Postgres and Valkey and run as uid 10001 and 1000, and the gateway applies
  `deploy/seed.yaml`, upstream OAuth client included. The `security` job's steps, run locally as written, pass. The
  three failures task 6.4 asks for were also shown locally: an AWS-shaped key in a new commit fails the gitleaks step;
  `FROM node:latest` fails the action's `hadolint.sh` (DL3007) and the pin test; an entry that expired yesterday
  fails the checker. The integration suite was not run locally: it needs the stack's fixed host ports, which a running
  development stack holds. It, the job on the pull request, GitHub's validation of `dependabot.yml`, and the linked
  failed runs of 6.4 stay open for CI.
