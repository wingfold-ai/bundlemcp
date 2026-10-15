# Tasks

## 1. One version source

- [x] 1.1 `main/app.py` and `api/mcp/protocol/server_info.py` read the version from the installed `bundlemcp`
  package instead of a literal; verify `cd apps/web && npm run openapi` leaves `openapi.json` unchanged and the
  `serverInfo` tests pass

## 2. The release script

- [x] 2.1 `tools/pull_request_release.py labels`: Conventional Commit title → `type:` and `semver:` labels, exit 1 with
  the expected form otherwise; verify with tests named for DEP-12 (feat, fix, `!`, docs, invalid title)
- [x] 2.2 Next-version rule, including the below-1.0 rule; verify with tests for `0.1.0` + major/minor/patch and
  `1.1.0` + each bump
- [x] 2.3 `apply`: rewrite `CHANGELOG.md` from `main`'s copy plus the entry (heading, date, protocol line, and either
      the given text or the branch's current one) and bump the two `pyproject.toml` files, `uv.lock` and `openapi.json`
      `info.version`; idempotent, and `none` restores `main`'s content; verify with tests over a temporary tree,
      including rerun and retitle, and that `release_notes.py --check` passes on the result
- [ ] 2.4 `tools/changelog_writer.py`: the Claude call with the entry schema, the diff filter and cut, rendering, and
  the title fallback when the call fails or the key is absent; verify with tests against a stubbed API (rendering,
  schema limits, no heading in a bullet, the fallback) and one manual run on a merged pull request's diff
- [x] 2.5 Hand-edit detection: compare the branch's entry text with the bot's newest commit on the branch; verify
  with tests over a temporary repository (unedited → regenerate, edited → keep, renumber keeps either)

## 3. Workflows

- [x] 3.1 `release.yml` accepts `workflow_call` with a `version` input beside its tag trigger; verify with
  `actionlint` and a manual run of the tag path being unchanged
- [x] 3.2 `release-entry.yml`: jobs **labels** and **entry** on `pull_request`, **refresh** and **tag** on `push` to
  `main`, with the permissions and concurrency from the design; verify with `actionlint`, and that
  `python3 tools/check_spec_ids.py` finds no code in its comments
- [x] 3.3 Create the `type:` and `semver:` labels in the repository; verify with `gh label list`. Ask the maintainer
  to add the `ANTHROPIC_API_KEY` secret; verify with `gh secret list`

## 4. Documentation

- [x] 4.1 `CONTRIBUTING.md`: replace *Cutting a release* with how a release happens, what CI owns on a branch, that an
      edited entry is kept, that the diff is sent to the Claude API, the fork case and `git pull --rebase`;
      `docs/self-hosting/deploy.md` and `docs/arc42/07-deployment-view.md` say every release-worthy merge is a release;
      verify with `rumdl check` and `check_docs_links.py`

## 5. Gates and first release

- [x] 5.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `rm -rf .import_linter_cache;
  uv run lint-imports`, the four `tools/check_*.py` scripts, `python3 tools/check_spec_ids.py`,
  `python3 tools/release_notes.py --check`, `cd apps/web && npm run openapi` (no diff) and
  `openspec validate --all --strict`; all pass
- [ ] 5.2 Open this change's pull request and verify the workflow, which runs from the branch, labels it, commits a
  `0.2.0` entry written by Claude and the bump without a second CI run; after the merge, verify the **tag** job tags
  `v0.2.0` and the release succeeds
