# Design

## Context

Two repository tools drive releases. Neither is part of the gateway's layers; both live in `tools/` and are tested
from `packages/bundlemcp/tests/infrastructure/`.

- `tools/pull_request_release.py` derives the `type:` and `semver:` labels from a PR title. It uses `BUMPS` (type to
  bump) and the `!` marker, and ignores the scope.
- `tools/release_notes.py` prints a tag's notes: the changelog entry, a rule, then the metering-hook protocol line. It
  already finds the previous release tag with `git describe --match v*.*.*`, which is what the compare link needs.
- `.github/workflows/release.yml` runs `gh release create "$TAG" --verify-tag --title "$TAG" --notes-file …` and
  leaves "latest" to GitHub's default.

See proposal.md for why.

## Goals / Non-Goals

**Goals:**

- The scope decides "no release" in one place: the same function that derives the labels.
- The frame is produced by the script that already produces the notes, so a release tagged by hand gets the same page.
- The latest decision is computed from tags, without asking the GitHub API, so it is hermetic to test.

**Non-Goals:**

- No hand-written highlights per release. The changelog entry is the content, and a longer story belongs in a blog
  post or a Discussions announcement.
- No new release tool (release-please, semantic-release). The existing flow already does what they do. This change
  only adopts their rule about which changes release.
- Dependency updates keep their current rule: Dependabot titles are `chore:` and release nothing. Whether a runtime
  dependency or base-image security bump should cut a patch release is a separate decision.

## Decisions

**Non-releasing scopes are a fixed set in `pull_request_release.py`: `ci`, `repo` and `docs`.** These are the scopes
whose changes never reach the `gateway` or `web` image. The set sits beside `BUMPS`, and the bump becomes
`"none" if scope in NO_RELEASE_SCOPES else …`. The alternative was to decide from the diff (release only when files
under `packages/` or `apps/` change). That is more accurate, but it makes the label depend on the file list, which
the labels job does not have from the title alone. It would also make a retitle no longer re-derive the labels
deterministically. The scope is what the author declares and reviewers read. A wrong scope is visible in the title
and fixed by editing it, which already re-runs the derivation.

**`!` does not override a non-releasing scope.** A breaking change to the repository's own tooling breaks no user. If
an author marks one breaking, the `type:` label still records it, but no version is cut.

**The frame lives in `release_notes.notes()`.** The function gains the previous tag (it already receives it) and the
repository slug, and assembles the parts in a fixed order:

1. the project sentence, held as a constant in the script: "bundlemcp is a self-hostable MCP gateway that turns
   all your MCP servers into one connector for any MCP client.";
2. the entry;
3. a *Run this version* block with both `ghcr.io/<owner>/bundlemcp-{gateway,web}:<version>` references;
4. the preview caveat when the major version is `0`;
5. one line of links: Quickstart, Documentation, Discussions (`https://github.com/<owner>/<repo>/discussions`);
6. `**Full Changelog**: https://github.com/<owner>/<repo>/compare/<previous>...<tag>`, omitted when there is no
   previous tag;
7. the existing protocol line, last, as DEP-12 already requires.

The owner and repository come from a `--repo owner/name` argument, which the workflow passes from
`$GITHUB_REPOSITORY`. Its default is `wingfold-ai/bundlemcp`, so local runs and tests need no environment. The docs
links point at `https://bundlemcp.dev`, the existing `VERSIONING` base. An alternative was to append GitHub's own
`--generate-notes` output. It lists PR titles, which repeats the entry in worse words, and it needs the API.

**Latest is decided by version order.** A new `--latest` flag on `release_notes.py` prints `true` when the tag is the
highest `v*.*.*` tag in the repository, and `false` otherwise. The workflow passes it as `gh release create
--latest=<value>`. GitHub's default compares creation date and semver loosely, and it has marked hotfixes of an older
line as latest in other projects. An explicit value removes the guess.

**The refresh of v0.4.0–v0.4.2 is a manual maintainer step, not a workflow.** It runs once. A
`workflow_dispatch` that rewrites published releases would be standing machinery for a one-off, and a permanent way
to overwrite public pages. The old tags do not contain the frame code, so the refresh runs the new script from
`main` and points it at each tag. The entry comes from `CHANGELOG.md` as it stands on `main`, not as the tag
shipped it. Corrections made after a release, such as the "first public preview" introduction added to the 0.4.0
entry in #219, should reach that release's page. The protocol version is read at the tag
(`git show <tag>:<hook source>`), so each release still states what it shipped. At release time the working tree
is the tag, so both readings agree and there is one code path. The maintainer runs
`python3 tools/release_notes.py <tag>` for each tag, reads the output, and then runs
`gh release edit <tag> --notes-file …`.

## Risks / Trade-offs

- [An author uses `fix(gateway)` for a CI-only change, or `fix(ci)` for a change to the image] → The scope is in the
  title, which reviewers read. CONTRIBUTING.md lists the three scopes and says what they mean. A mistaken label is
  fixed by retitling before merge.
- [The project sentence drifts from the repository description and the message house] → It is one constant, written
  client-neutral ("any MCP client"), and the release tests assert the frame, not the wording, so updating it is a
  one-line change.
- [v0.4.2 stays "Latest" until the next user-facing release, and its entry is still about CI] → After the refresh
  its page carries the full frame, so a visitor still learns what bundlemcp is and where to start. The next release
  that changes an image replaces it.
- [Editing published release bodies changes public pages] → Done once, by hand, after the maintainer approved the
  generated text. Tags, assets and images are untouched.

## Migration Plan

1. Merge the change with a `ci`-scoped title. Under the new rule it cuts no release itself.
2. Approve and run the refresh of v0.4.0–v0.4.2.
3. Rollback: revert the commit. Already-edited release bodies can be restored from the changelog with the previous
   script version if needed.
