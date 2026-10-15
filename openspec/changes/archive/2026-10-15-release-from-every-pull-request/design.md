# Design: release from every pull request

## Context

See [proposal.md](proposal.md) for why. What exists today:

- `release.yml` runs on a pushed `v*.*.*` tag: `release_notes.py <tag>` checks the entry, then the restore rehearsal,
  `publish.yml` (images `:<version>`) and `gh release create`. `ci.yml` runs `release_notes.py --check`.
- The version `0.1.0` is written in five places: both `pyproject.toml` files, `uv.lock` (`bundlemcp` and
  `bundlemcp-workspace`), `main/app.py` (`FastAPI(version=...)`, which `npm run openapi` copies into
  `apps/web/openapi.json` `info.version`) and `api/mcp/protocol/server_info.py` (`SERVER_VERSION`).
- Repository workflow permissions default to `read`. The `main` ruleset requires squash merges and resolved review
  threads, but no status check; `ci-passed` is the job meant to be required.
- No `type:`/`semver:` labels exist beyond the issue labels `type: bug` and `type: feature`.
- GitHub starts no workflow for events caused by the workflow token (`GITHUB_TOKEN`), except `workflow_dispatch` and
  `repository_dispatch`. That is what keeps the entry commit from rerunning CI, and it is also why a tag pushed by a
  job cannot start `release.yml` through its `push: tags` trigger.

This is repository tooling, outside the library's layers: everything new lives in `tools/` and `.github/workflows/`,
and the only library edit is in `main/` and `api/`, where the version is read.

## Goals / Non-Goals

**Goals:**

- One squash commit per pull request on `main`, carrying the entry and the bump.
- The version and labels are derived from the title alone, by one script that is unit-tested; the entry's text comes
  from the diff, and a person's edit to it outlives every later push.
- The entry's version never collides: whichever pull request merges first takes the next version, and the rest move up.

**Non-Goals:**

- Letting the model decide the version. The bump comes from the title, so a reviewer sees it in the labels and the
  model can only change wording.
- A merge queue. It would let CI test the merged result, but the entry commit cannot be made inside a merge group.
- Releasing pull requests from forks automatically.

## Decisions

### Two scripts: placement and text

`tools/pull_request_release.py`, beside `release_notes.py`, is pure over its inputs, so the tests need no GitHub and no
model:

| Subcommand | Input | Output |
|---|---|---|
| `labels "<title>"` | the title | `type: <t>` and `semver: <s>`, or exit 1 with the expected form |
| `apply --title … --number … --url … --date … [--text FILE]` | the working tree at the branch with `main` merged in; the entry's text, or none to keep the branch's | merges `main` in, drops the entries `main` lacks, inserts this pull request's entry, sets the version files; prints the version, or nothing for `none` |

`apply` merges `main` into the branch first; a conflict in `CHANGELOG.md` or a version file takes `main`'s side,
since `apply` rewrites them next, and a conflict anywhere else aborts the merge and is left to the author. It then
removes every entry `main` does not have (the ones CI added) and inserts this pull request's entry above the newest
release, so a rerun is idempotent and the branch's own edits elsewhere in the changelog survive. The version is `main`'s
raised by the title, written into each version file. The entry's current text is read relative to the merge-base before
merging; without `--text` it is carried over unchanged, which is how renumbering keeps an edited or generated text. The
type → bump rule lives here only.

`tools/changelog_writer.py` writes the text. It calls the Anthropic Messages API (`claude-sonnet-5-5`) with the title,
the description and the diff, and asks for the entry through a tool whose input schema is the entry itself: arrays of
bullets for *Added*, *Changed*, *Fixed* and *Security*, each bullet a string of at most 400 characters, at most eight
per section, and a `breaking` string. The script renders those into Markdown, escaping nothing but checking that no
bullet starts a heading, so the model can only produce bullets. The prompt carries the changelog's style (what a user,
operator or integrator gets, no file lists, the 0.1.0 entry as an example) and the rule that requirement codes never
appear. The diff is the pull request's three-dot diff without `uv.lock`, `package-lock.json`, `apps/web/openapi.json`,
`apps/web/types/api.d.ts` and `CHANGELOG.md`, cut at 150 000 characters with a note that it was cut.

*Alternative: claude-code-action.* It lets Claude read beyond the diff, but runs an agent with tool access on the
checkout; a single API call with a fixed schema is easier to bound. *Alternative: release-please or semantic-release.*
Both compute from the commits on `main` after the merge, so the entry arrives as a second commit or a separate release
pull request, which the maintainer ruled out.

### When the text is rewritten

The text is generated on `opened`, `reopened` and on `synchronize` caused by someone other than the bot; renumbering
(`edited`, a move of `main`) never calls the model. Before generating, the job compares the branch's entry text with
the text of the same entry in the newest commit the bot made on the branch. When they differ, a person edited it, and
the text is kept from then on: later pushes only renumber. No marker is written into `CHANGELOG.md`, so nothing of
this reaches `main`. A description edit alone does not regenerate; the next push picks it up.

When the call fails or `ANTHROPIC_API_KEY` is absent, the text is the title's subject with the link, under the section
its type maps to, and the job adds a warning annotation. The release is never held up by the model.

### The diff is untrusted input

The diff and description are written by the pull request's author and reach the model's prompt, so they can carry
instructions. What the model can do with them is limited to the schema above: it returns bullets, the job writes them
into one entry of `CHANGELOG.md`, and the job's token can push only to that branch. The API key is the only secret the
job reads, it goes in a header and is never echoed, and fork pull requests receive no secrets at all. The entry is
reviewed with the rest of the pull request before the merge publishes it.
### One version source in the code

`app.py` and `server_info.py` read `importlib.metadata.version("bundlemcp")`. A bump then touches the two
`pyproject.toml` files, `uv.lock` and the `info.version` line of `apps/web/openapi.json`; `apply` edits those four by
pattern instead of running `uv lock` and `npm run openapi`, so the job needs neither Python dependencies nor Node.
The OpenAPI drift gate still passes, because the regenerated document reads the same version from the package.

### The workflow, `release-entry.yml`

- `pull_request` (`opened`, `edited`, `synchronize`, `reopened`): job **labels** runs `labels` and sets the labels
  with `gh` (`pull-requests: write`). Job **entry** checks out the head branch with a writable token, merges
  `origin/main` if the branch is behind, runs `changelog_writer.py` when the text is due (above) and `apply`, and pushes
  one commit, `chore(repo): Release <version>`, when
  anything changed (`contents: write`). `pull_request` rather than `pull_request_target`, so a fork's code never runs
  with a writable token; on a fork the token is read-only, the push fails, and the job's error says what to do.
- `push` to `main`: job **refresh** runs `apply` again for every open pull request whose `semver:` label is not
  `none`, after merging `main` into its branch. A merge that conflicts outside `CHANGELOG.md` and the version files is
  left to the author: the job comments once on the pull request and moves on. Conflicts inside those files are
  resolved by `apply`, which rewrites them from `main` anyway.
- A `concurrency` group per pull request, `cancel-in-progress`, so a burst of edits leaves one push.

Merging `main` into the branch creates a merge commit on the branch; the squash merge removes it from `main`'s history,
so the history the maintainer asked to keep clean is unaffected.

### Releasing on `main`

`release.yml` gains `workflow_call` with a `version` input, beside its `push: tags` trigger, and reads the version
from the input or the tag. A job **tag** in `release-entry.yml`, on `push` to `main`, compares the package version with
the newest `v*` tag; when it is higher it creates and pushes the tag, then calls `release.yml` with the version. A
`semver:` label other than `none` merged without a bump (a fork, or a failed entry job) fails this job: the version is
the only signal, so nothing is released, and the failure is visible on `main`.

### CI sees the commit before the entry

`ci.yml` runs on the author's commit. Pushing with the workflow token is not enough to keep the entry commit from
running: GitHub still creates `pull_request` runs for it and holds them as *action required*, which leaves two pending
checks on the pull request's head. So every commit CI pushes to a branch, the merge of `main` included, says
`[skip ci]` in its subject, and GitHub creates no run at all. The squash merge takes its message from the pull request
body (the repository's `squash_merge_commit_message` is `PR_BODY`), so the marker never reaches `main`, where it would
skip CI, the image publish and this workflow's **tag** job.

The ruleset requires no status check today, so a head without checks does not block the merge. If `ci-passed` is made
required, job **entry** also sets a `ci-passed` commit status on the new head, but only after the run for the parent
commit succeeded and only when the new commit changes nothing but the files `apply` owns (`statuses: write`). That is
left out of the first cut, because the ruleset does not need it.

### The Claude API key

The key may be scoped to a workspace or to the organization. An organization-scoped key must name the workspace on each
request, so the job also passes the repository variable `ANTHROPIC_WORKSPACE_ID`, when set, as the
`anthropic-workspace-id` header. A workspace ID is not a secret; the key stays one.

## Risks / Trade-offs

- **The model misdescribes a change.** → The entry is part of the reviewed diff, and an edit to it is kept. The model
  never decides the version.
- **Cost and data.** One call per author push, Sonnet, at most about 40 000 tokens in. The repository is private, so
  the diff leaves GitHub for the Claude API under the account's data terms. → `CONTRIBUTING.md` says so; deleting the
  secret turns it off and falls back to title bullets.
- **The tested commit is not the merged one.** CI tested the author's commit; the merged commit adds the entry, the
  bump and possibly `main`. → `apply` touches only text files that no test reads except `release_notes.py --check`,
  which `apply` runs itself before pushing. A merge of `main` is what any behind-but-mergeable pull request is today.
- **The bot writes to contributors' branches.** An author who pushes without pulling gets a non-fast-forward error. →
  `CONTRIBUTING.md` says CI owns those lines and that `git pull --rebase` is the fix. The ruleset's `non_fast_forward`
  rule applies to `main` only.
- **The date is the day the entry was last generated**, not necessarily the merge day. → Every push and every move of
  `main` regenerates it; a pull request that sits unchanged for a week keeps its older date. Accepted.
- **`[skip ci]` on `main`.** If the squash message went back to listing the commit messages, the bot's subjects would
  land on `main` and skip its workflows, release included. → `CONTRIBUTING.md` names the setting, and a skipped
  release is visible as a merge with no tag.
- **Two merges in quick succession.** The second pull request's entry may still name the first one's version if its
  refresh has not run yet. → The squash merge then conflicts in `CHANGELOG.md`, and GitHub refuses it until the
  refresh has run. No duplicate tag can be created.

## Migration Plan

1. Add the `ANTHROPIC_API_KEY` repository secret (the maintainer, in the repository settings; never in a file), and
   for an organization-scoped key the `ANTHROPIC_WORKSPACE_ID` variable. Set the squash message to the pull request
   body.
2. Create the labels (`type: feat` … `type: revert`, `semver: major|minor|patch|none`) with `gh label create`.
3. Land this change through its own pull request. A `pull_request` workflow runs from the pull request's own
   branch, so `release-entry.yml` already runs for it: it labels the pull request, has Claude write the `0.2.0` entry
   and bumps the version. That run is the end-to-end test of the entry half. The **tag** and **release** jobs run from
   `main` once it is merged, which tests the other half.
4. Rollback: delete `release-entry.yml`. `release.yml`'s tag trigger still works, and releases go back to the manual
   steps.
