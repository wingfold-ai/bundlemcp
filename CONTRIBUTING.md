# Contributing to bundlemcp

Thanks for taking the time to contribute. This guide explains how to report problems, find your way around the
documentation, and get a change merged: the order to read things in, the checklist a change has to pass, and how to
open a pull request. Coding conventions are in [CLAUDE.md](CLAUDE.md) and the rule files it points at.

## Ways to contribute

- **Report a bug** with the bug report form in the issue tracker.
- **Suggest a feature** with the feature request form. For open-ended ideas or questions, open an issue describing the
  problem you want to solve first.
- **Improve the documentation.** Small fixes need no issue first.
- **Fix an issue.** Issues labelled `good first issue` are a good place to start; `help wanted` marks work the
  maintainers would like help with.

Security problems are the exception: never open a public issue for them. Follow [SECURITY.md](SECURITY.md).

## Read these, in this order

You do not need all of it before your first change. The first four are the orientation; the rest are read when you
touch the thing they describe.

1. [`README.md`](README.md) — what this is and where things are.
2. [`openspec/README.md`](openspec/README.md) — the product in one file, the capability index, and the decision log,
   which records what was deliberately left out. Read the log before proposing a feature.
3. [`packages/bundlemcp/README.md`](packages/bundlemcp/README.md) — the layer map. This is the most useful single
   document for finding your way around, and it is the authoritative description of what each package holds.
4. [`docs/arc42/04-solution-strategy.md`](docs/arc42/04-solution-strategy.md) and
   [`06-runtime-view.md`](docs/arc42/06-runtime-view.md) — why the architecture is shaped this way, and four scenarios
   traced end to end. Twelve lines and four scenarios, and between them they explain most of the design.
5. [ADR-0033](docs/adr/0033-clean-architecture-layers.md) and
   [ADR-0034](docs/adr/0034-pydantic-entities-and-row-classes.md) — the layer rule and the entity/row split, which
   together explain most "why is this file here" questions.
6. The rule file for the layer you are touching, from [`.claude/docs/`](.claude/docs/): `controllers.md` for an HTTP
   surface or an MCP method, `pydantic-models.md` and `pydantic-fields.md` for any model, `module-naming.md` before
   creating a file, `design-principles.md` for naming and pattern choices.
7. [`packages/bundlemcp/bundlemcp/api/mcp/README.md`](packages/bundlemcp/bundlemcp/api/mcp/README.md) — only if you
   are working on the MCP gateway itself, where it is the deep dive. Parts of its lower half still describe the
   pre-ADR-0033 layout; trust
   [ADR-0035](docs/adr/0035-front-controller-protocol-adapters-and-admission-pipeline.md) where they disagree.

The corpora and what each is for:

| Where | Question it answers | Rule |
|---|---|---|
| `openspec/specs/` | **What** is true today, with testable requirement IDs | Normative. Changed only by archiving a change |
| `openspec/changes/` | **What will change** — proposal, delta specs, design, tasks | New behaviour starts here |
| `docs/arc42/` | **Why** it is built this way, current state | Rationale, not requirements |
| `docs/adr/` | **When and why not** — one decision each, with alternatives | Append-only |
| `.claude/docs/` | **How to write it** — conventions | Loaded into every AI session, so keep it true |
| `docs/{guide,self-hosting,manage,connect,integrate}/` | The published site, for users and operators | Describes shipped behaviour only |

## Development setup

```bash
git clone https://github.com/wingfold-ai/bundlemcp.git
cd bundlemcp
uv sync --all-packages     # Python >= 3.13 workspace (gateway + library); CI and images use 3.15
```

The admin UI and the docs site need Node 24 or later; `apps/web` refuses an older one on `npm ci`.

The full stack (gateway, web UI, Postgres, Valkey, a dev OIDC provider), when you need the real thing:

```bash
cp deploy/.env.example deploy/.env
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build --wait
```

For everyday work, run the infrastructure in compose and the gateway on the host, so a change does not mean an image
rebuild:

```bash
docker compose -f deploy/docker-compose.yml up -d postgres valkey keycloak
uv run uvicorn --factory apps.gateway.main:app_factory --reload --no-proxy-headers
```

The admin UI:

```bash
cd apps/web && npm ci && npm run dev
```

## Making a change

1. Fork the repository and create a branch from `main`; never commit to `main` directly.
2. Keep the change focused. One pull request should do one thing.
3. Add or update tests for the behaviour you change.
4. Run the checklist below locally before you push.

### The checklist

Every item is already enforced somewhere — CI, a hook, or review. Running them locally is faster than finding out from
CI.

```bash
uv run pytest -q                        # must pass
uv run ruff check .                     # must be clean
uv run lint-imports                     # 3 contracts, 0 exceptions
uv run rumdl check .                    # Markdown line length 120; `uv run rumdl fmt .` rewraps
cd apps/web && npm run openapi          # regenerates openapi.json + types/api.d.ts
cd apps/web && npm run typecheck        # vue-tsc; the build alone does not catch type errors
python3 tools/check_docs_links.py       # relative links and heading anchors
python3 tools/check_docs_symbols.py     # the living docs name no dead symbols
python3 tools/check_docs_settings.py    # env vars and requirement IDs are real
python3 tools/check_adr_graph.py        # ADR statuses and indexes agree
python3 tools/check_spec_ids.py         # requirement codes are well-formed, unique and real
python3 tools/release_notes.py --check  # CHANGELOG.md entries have dated headings, newest first
openspec validate --all --strict        # specs and changes are well-formed
```

And in the pull request:

- [ ] **A change proposal first** if behaviour changes: `openspec/changes/<change>/` with proposal, delta specs, design
      (when not obvious) and tasks — see [openspec/README.md](openspec/README.md#making-a-change). Keep requirement IDs
      (`UPS-1`, `EP-3`, …) stable. Archive the change into `openspec/specs/` once it is implemented, and keep
      `openspec validate --all --strict` passing.
- [ ] **An ADR in the same PR** if the change makes or reverses an architectural decision (DOC-11). Use
      [ADR-0034](docs/adr/0034-pydantic-entities-and-row-classes.md) as the template — real alternatives with real
      reasons, and honest trade-offs.
- [ ] **A rename ADR also updates the docs that name the symbol**, including `.claude/docs/` and `docs/arc42/`. This is
      the step that has been missed before, which is what `tools/check_docs_symbols.py` now catches.
- [ ] **Update the LikeC4 model** if the structure changed (`npx likec4 validate docs/likec4`).
- [ ] **Docs in the same PR** as the behaviour they describe (DOC-5).
- [ ] Tests reference the requirement ID they verify, in the name or docstring.
- [ ] No `Co-Authored-By: Claude` trailer and no AI attribution line — see
      [`.claude/docs/git-attribution.md`](.claude/docs/git-attribution.md).

### Commit and pull request titles

Pull requests are squash-merged, so the **pull request title** becomes the commit message. Write it in the
[Conventional Commits](https://www.conventionalcommits.org/) style:

```
fix(parser): handle empty input
feat: add --json output
docs: explain the retry setting
```

Use `feat` for new behaviour, `fix` for bug fixes, and `docs`, `test`, `refactor`, `chore`, `ci` or `build` for the
rest. Mark a breaking change with `!` (`feat!: drop Node 18`) and describe the migration in the pull request body.

## Tests

Four hermetic tiers under `packages/bundlemcp/tests/`, plus integration tests at the root. `testpaths` points at the
hermetic ones, so bare `pytest` runs them.

| Tier | Path | Runs on | Run just it |
|---|---|---|---|
| Domain | `packages/bundlemcp/tests/domain` | Pure objects | `uv run pytest packages/bundlemcp/tests/domain` |
| Application | `packages/bundlemcp/tests/application` | `infrastructure/memory` fakes | `… tests/application` |
| Infrastructure | `packages/bundlemcp/tests/infrastructure` | SQLite and fakeredis | `… tests/infrastructure` |
| API | `packages/bundlemcp/tests/api` | The ASGI app, no network | `… tests/api` |
| Integration | `tests/integration` | The compose stack | `BUNDLEMCP_INTEGRATION=1 uv run pytest tests/integration -q -m "not fleet"` |

Note the paths: `uv run pytest tests/domain` collects nothing, because the hermetic tiers live under
`packages/bundlemcp/`. [deploy/TESTING.md](deploy/TESTING.md) covers the integration suite.

Writing one: copy the nearest existing test in the tier. Application tests build their collaborators from
`infrastructure/memory`; API tests go through the ASGI app with the fixtures in `packages/bundlemcp/tests/conftest.py`.
The `fleet` marker means an integration test needs private images and is skipped in CI.

Browser tests are Playwright, in `apps/web/tests/`, with `npm run test:ui`. `apps/web/tests/TESTMAP.md` maps them to
requirement IDs and is regenerated with `npm run test:map`.

### MCP conformance

`tests/conformance/run_conformance.py` runs the MCP project's published server conformance suite through the gateway.
The suite checks fixed fixtures (`test_simple_text`, `test://static-text`, …), which
[`examples/conformance-mcp`](examples/conformance-mcp/server.py) serves; the harness bundles it behind an open
`conformance` endpoint and presents each fixture tool under its own name.

```bash
docker compose -f deploy/docker-compose.yml --profile conformance up -d --build --wait gateway conformance-mcp
uv run python tests/conformance/run_conformance.py --revision 2025-11-25
uv run python tests/conformance/run_conformance.py --list-revisions   # what CI runs
```

CI runs it once per served revision the suite has scenarios for, a list read from the gateway's own registry, so a new
revision joins the matrix as soon as the suite covers it; that run is the conformance step of adding a revision
(PROT-22). [`tests/conformance/baseline.yml`](tests/conformance/baseline.yml) lists what the gateway fails by design,
each with its reason. A new failure fails the job, and so does a listed scenario that passes: remove its entry. To move
to a newer suite, change the pinned suite version at the top of the harness.

## Adding a database column

The column is declared **twice** — once on the entity, once on the row class — and the repository maps between them
(ADR-0034). Then:

```bash
# 1. add the field to the entity in domain/<context>/ and to the row in
#    infrastructure/postgres/rows/, and map it in the repository
# 2. autogenerate the migration
cd packages/bundlemcp
uv run alembic revision --autogenerate -m "bundle overview"
# 3. read the generated file before committing it
```

Autogenerate sees the table because `infrastructure/postgres/migrations/env.py` imports the whole `rows` package; a row
class that nothing imports is invisible to it.

Migrations must be **backward compatible one release back** (DEP-4/5), because a rolling deploy runs old and
new replicas against the same schema. In practice: add nullable columns or columns with defaults, and split a rename
into add–backfill–drop across two releases. Every replica runs `alembic upgrade head` on boot, guarded by a Postgres
advisory lock, so concurrent starts are safe.

## Working on `apps/web`

The admin UI is a client of the same API you can script against. The part that catches backend contributors out:

**A DTO change is a frontend change.** `apps/web/openapi.json` and `apps/web/types/api.d.ts` are generated, never
hand-written, and CI fails on a stale copy of either. `npm run typecheck` passes while that gate fails, so run
`npm run openapi` after touching anything in `application/schemas/` or a route signature, and commit both generated
files.

**Pages read through the query layer.** A page reads management data with `useQuery` (`app/composables/useQuery.ts`),
under a key from `app/utils/queryKeys.ts` — `resource` or `resource:parameter…`; the shared lists have their own
composables in `app/composables/useManagementQueries.ts`. A revisited page renders its cached result at once and
refetches it in the background. A mutation never reloads its page by hand: it calls `invalidate(...)` with every
resource it changes, and every view of that data refreshes, on screen now or when next shown.

**Naming rules come from the schema.** Form validation calls `nameProblem` (`app/utils/resourceNames.ts`), which reads
the patterns, the `__` rule and the reserved endpoint names from `openapi.json`. A rule changed in
`domain/shared/resource_names.py` reaches the forms with the next `npm run openapi`; never copy one into the frontend.

## Debugging

- **Logs** are structured JSON carrying a request id, the endpoint and the caller, and never secrets. Pipe them through
  `jq` locally.
- **`/api/v1/docs`** is a live OpenAPI UI against your running gateway — the fastest way to check a route's real shape.
- **Live state** is in Valkey under `bmcp:*`: `docker compose exec valkey valkey-cli --scan --pattern 'bmcp:*'`.
- **Two replicas**, to reproduce a cross-replica bug: start a second gateway on another port against the same Postgres
  and Valkey. Everything except an open stream must work identically on either.
- **`lint-imports` failures** name the contract they broke. The usual fixes, in order of preference: move the symbol
  to the layer it belongs in, inject it through a contract instead of importing it, or introduce a contract. Never
  `ignore_imports`. Delete `.import_linter_cache` after moving modules — a stale cache reports contracts as kept when
  they are broken.

CI runs all of these on every pull request, plus the frontend build, the docs build, LikeC4 validation, both image
builds and the integration suite against the compose stack; one `ci-passed` check requires every job.

## How a release happens

Every pull request into `main` carries the release its merge makes; nobody cuts one by hand.
`.github/workflows/release-entry.yml` does the work:

1. **The title decides the version.** The title must be a Conventional Commit (`feat(bundles): Order members by
   hand`, at most 72 characters). CI labels the pull request `type: <type>` and `semver: <bump>` from it, and again
   whenever the title is edited: `!` is `major`, `feat` is `minor`, `fix`, `perf` and `revert` are `patch`, everything
   else is `none`. Below 1.0 each bump moves one place to the right: a breaking change takes `0.1.0` to `0.2.0`, a
   feature or fix to `0.1.1`. Reaching `1.0.0` is a pull request of its own.
2. **CI commits the entry to your branch.** For any bump but `none`, CI pushes one commit,
   `chore(repo): Release <version>`, adding the `## [<version>] - <date>` entry to `CHANGELOG.md` and raising the
   version in both `pyproject.toml` files, `uv.lock` and `apps/web/openapi.json`. That commit says `[skip ci]`, so it
   starts no CI run; the squash merge takes its message from the pull request body, so the marker never reaches `main`.
   Its text is written by Claude from your diff and description, so it says what users get rather than repeating the
   title; the diff and description are sent to the Claude API to write it. Reword it on the branch if you like: once the
   text differs from what CI last wrote, CI keeps yours and only renumbers it. Without your edit, CI rewrites the text
   on each push.
3. **CI keeps the version free.** When the title changes or `main` moves on, CI merges `main` into your branch and
   renumbers the entry above the newest release. If that merge conflicts outside the changelog and the version files,
   CI comments once; merge or rebase onto `main` yourself, and your next push renumbers it.
4. **The merge releases.** The squash commit carries the entry and the bump. On `main`, CI tags `v<version>` and runs
   `.github/workflows/release.yml`: it rehearses the documented restore against the compose stack
   (`restore-rehearsal.yml`), publishes both images as `:<version>`, and creates the GitHub release from the entry,
   ending with the metering-hook protocol version and whether it changed since the previous release. A failed
   rehearsal publishes nothing. A `semver: none` pull request releases nothing.

What this means while you work on a branch:

- CI owns the release entry and the version lines; a hand edit to the version is replaced. Pull before you push
  (`git pull --rebase`), because CI may have pushed to your branch since your last pull.
- A release that changes the metering-hook protocol bumps `METERING_PROTOCOL_VERSION` in
  `application/metering/metering_hook.py` in the same pull request, and its title is marked breaking (`!`); CI refuses
  the entry otherwise. The entry then says the protocol changed, with a breaking bullet CI adds unless the text already
  names it. An entry names the protocol only in that case.
- `main` only accepts a pull request whose `ci-passed` check succeeded. CI's own commits run no CI, so the result CI
  reached on the commit before them is set on the head as `ci-passed`: by the `ci-passed` job itself when it finishes,
  or by the job that pushed CI's commit when CI was already done. Until then the check is pending and the merge waits.
- Never write a CI-skip marker (`[skip ci]` and its variants) in a pull request's description: the squash merge takes
  its message from the description, and on `main` the marker skips CI, the image publish and the release. The title
  check fails on one.
- CI cannot push to a fork. A pull request from a fork fails its entry check; a maintainer moves the branch into the
  repository before merging.
- `python3 tools/release_notes.py v1.2.0` prints what a release will say. A tag pushed by hand (`git tag v1.2.0 && git
  push origin v1.2.0`) still runs the same release, as long as the changelog has its entry.

## Opening a pull request

- Fill in the pull request template and link the issue it resolves.
- CI must pass. If a check fails for a reason unrelated to your change, say so in the pull request.
- A maintainer reviews every pull request. Expect a first response within a week; feel free to leave a comment if it
  takes longer.
- Review comments are about the code, not about you. Push follow-up commits rather than force-pushing, so reviewers can
  see what changed.

## Where to ask

Open an issue. If it is about a decision rather than a defect, check the [spec decision log](openspec/README.md) and the
[ADR index](docs/adr/README.md) first — a surprising number of "why not X" questions are answered there, with the
reason.

## Licensing of contributions

By contributing you agree that your contribution is licensed under the same terms as the project
([Apache-2.0](LICENSE)).

## Code of Conduct

This project follows a [Code of Conduct](CODE_OF_CONDUCT.md). By taking part you agree to uphold it.
