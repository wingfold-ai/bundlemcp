# Proposal

## Why

The "Latest" release should be the page to link to, but today it often is not. A change only to how bundlemcp is
built, such as `fix(ci): Defuse CI-skip markers that Dependabot quotes` (#226), counts as a patch, so it cut v0.4.1
and v0.4.2. Each rebuilt the images and published a release page whose whole content is a CI workaround. The release
notes are also only the changelog entry, so a newcomer who lands on any release page learns nothing about what
bundlemcp is, how to upgrade or where to give feedback. Mature projects using release-please, semantic-release or
changesets avoid both problems. Only changes a user can notice cut a release, and every release page has the same
frame around its changelog entry. Then the newest release, reached through the stable
`https://github.com/wingfold-ai/bundlemcp/releases/latest` link, is always worth sending someone to.

## What Changes

- **Only user-facing changes release.** A pull request whose title has the scope `ci`, `repo` or `docs` is labelled
  `semver: none`, whatever its type and even when marked breaking, so it gets no changelog entry, no version bump and
  no release. None of these changes reaches a released image. The documentation site publishes from `main` on its
  own, so a docs fix reaches readers without a release. Titles without one of these scopes derive their bump as
  before.
- **Every release page explains itself.** The release notes frame the changelog entry with the same parts each time:
  - before the entry, a one-line description of bundlemcp;
  - after it, how to run this version (both image references), the preview caveat while the version is below 1.0,
    links to the quickstart, the documentation and GitHub Discussions, and a *Full Changelog* link that compares this
    tag with the previous release tag;
  - last, as today, the metering-hook protocol line.
- **"Latest" is explicit.** The release step marks a release as GitHub's latest only when its version is the highest
  release tag. A patch tagged by hand for an older line does not take over the link.
- **One-time refresh.** The bodies of the already-published v0.4.0, v0.4.1 and v0.4.2 releases are regenerated with
  the new notes, so the current "Latest" page has the frame too. This edits public pages, so a maintainer runs it by
  hand after approving the output. Releases before v0.4.0 predate the public repository and are left as they are.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `deployment`:
  - modifies DEP-11 (image publishing): the release notes carry the standard frame, and the release is marked latest
    only when it is the highest version.
  - modifies DEP-12 (every pull request carries its release): the scopes `ci`, `repo` and `docs` release nothing.

## Impact

- `tools/pull_request_release.py`: the set of scopes that never release, used when deriving the `semver:` label. Its
  tests are in `packages/bundlemcp/tests/infrastructure/test_pull_request_release.py`.
- `tools/release_notes.py`: the frame around the entry, the compare link and the latest decision. Its tests are in
  `packages/bundlemcp/tests/infrastructure/test_release_notes.py`.
- `.github/workflows/release.yml`: passes `--latest` or `--latest=false` from the script's decision.
- `CONTRIBUTING.md` (how a release happens, and the scopes that release nothing).
- Published GitHub releases v0.4.0–v0.4.2: bodies edited once, by hand, after approval.
- No gateway behaviour changes. No ADR: this refines the existing release flow and makes no new architectural
  decision.
