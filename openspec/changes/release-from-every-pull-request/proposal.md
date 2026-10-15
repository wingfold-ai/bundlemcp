# Proposal: release from every pull request

## Why

A release today is a manual step: someone writes the `CHANGELOG.md` entry, chooses the version, merges it, then tags.
The information is already there. Every squash subject on `main` is a Conventional Commit, so the type of each change,
and whether it is breaking, is known when its pull request is opened. Working out the version by hand and writing the
entry again duplicates that, and changes pile up unreleased between releases. The maintainer wants every merge into
`main` to be a release whose version follows from the pull request, and the changelog to stay in the repository, with
no extra commits on `main` beyond the one squash commit per pull request.

## What Changes

- **Labels from the title:** an action derives `type: <type>` and `semver: major|minor|patch|none` labels from the
  pull request's Conventional Commit title, re-deriving them whenever the title is edited. `!` means major. A title
  that is not a Conventional Commit fails the check. The labels are what the version is computed from.
- **Versioning below 1.0:** while the version is `0.x`, a major bump raises the minor (`0.1.0` → `0.2.0`) and a minor
  or patch bump raises the patch. `1.0.0` is reached by a deliberate pull request, not as a side effect.
- **The entry lands in the pull request:** while the pull request's CI runs, a job commits to its branch the
  `## [x.y.z] - <date>` entry in `CHANGELOG.md` (with the metering-hook protocol line) and the version bump. The commit
  uses the workflow token, so CI does not run again. The title only decides the version; the entry's text is written
  by Claude from the pull request's diff and description, sorted into *Added*, *Changed*, *Fixed* and *Security*. It
  is rewritten when the author pushes, unless someone edited it on the branch, in which case the edit is kept. When
  the title changes or `main` moves on, only the version and date are renumbered, so the version is always the next
  free one. The squash merge therefore carries the entry and the bump.
- **Merge releases:** a job on `main` sees the version raised, tags `vX.Y.Z` and runs the existing release
  (restore rehearsal, versioned images, GitHub release from the entry). A `semver: none` pull request (`docs`, `test`,
  `ci`, `build`, `chore`, `refactor`) gets no entry and no release.
- **One version source:** the gateway's reported version (OpenAPI `info.version`, MCP `serverInfo.version`) is read
  from the installed package, so a bump changes `pyproject.toml` and the lock file, plus the version line in the
  generated `apps/web/openapi.json`.
- `CONTRIBUTING.md`'s *Cutting a release* becomes *How a release happens*: nothing is cut by hand.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `deployment`: DEP-11 (a release tag is created by the merge that raises the version, not pushed by hand); ADDED
  DEP-12 (every pull request carries its own release: labels from the title, the version rule, the entry committed to
  the branch).

## Impact

- **CI:** a new `.github/workflows/release-entry.yml` (labels plus the entry commit on pull requests, and the refresh of
  open pull requests when `main` moves); `.github/workflows/release.yml` becomes callable (`workflow_call`) and is
  called by a tagging job on `main`, because a tag pushed with the workflow token starts no workflow.
- **Repository:** a new `tools/pull_request_release.py` (title → labels, next version, entry placement, bump) and
  `tools/changelog_writer.py` (the Claude call that writes the entry's text) with tests beside
  `test_release_notes.py`; labels `type: feat` … and `semver: major|minor|patch|none` created in the repository;
  `packages/bundlemcp/bundlemcp/main/app.py` and `api/mcp/protocol/server_info.py` read the package version.
- **Settings:** the repository's workflow permissions stay `read` by default; the new jobs ask for `contents: write`
  and `pull-requests: write` themselves. An `ANTHROPIC_API_KEY` repository secret, added by the maintainer, lets the
  job call the Claude API; the pull request's diff and description are sent to it.
- **Docs:** `CONTRIBUTING.md` (how a release happens, what the bot owns), `docs/self-hosting/deploy.md` (every
  release-worthy merge is a release), `docs/arc42/07-deployment-view.md` (the releases row).
- **No ADR:** this changes the release procedure, not the architecture, the same reasoning as
  [complete-release-engineering](../archive/2026-10-15-complete-release-engineering/proposal.md).
