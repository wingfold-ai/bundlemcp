# Spec Delta

## MODIFIED Requirements

### Requirement: DEP-12 Every pull request carries its release
A pull request into `main` SHALL carry the release its merge makes, so the squash commit is the release commit and
`main` gains no other commit for it.

- **Labels from the title.** The pull request's title MUST be a Conventional Commit (`<type>(<scope>)!: <Subject>`). CI
  derives a `type: <type>` label and a `semver:` label from it, and replaces both whenever the title is edited: `!` is
  `semver: major`; otherwise `feat` is `minor`, `fix`, `perf` and `revert` are `patch`, and every other type is `none`.
  A title that is not a Conventional Commit fails the check and gets no labels. A description that contains a CI-skip
  marker (`[skip ci]` and its variants) fails the check too, because the squash merge takes its message from the
  description and the marker would skip CI and the release on `main`. A title is at most 72 characters. A title
  Dependabot wrote that is longer is shortened by CI before it is checked, losing only what the diff already shows:
  first the group and directory count Dependabot appends, then the version updated from, then the directory, until it
  fits. CI saves the shortened title on the pull request, so the squash commit carries it.
- **Next version.** The pull request's version is the version on `main` raised by its `semver:` label. While the major
  version is `0`, a major bump raises the minor and a minor or patch bump raises the patch (`0.1.0` → `0.2.0` and
  `0.1.1`); from `1.0.0` the bumps are literal.
- **Entry and bump on the branch.** For a `semver:` label other than `none`, CI commits to the pull request's branch a
  `CHANGELOG.md` entry `## [<version>] - <date>`, placed above the newest entry on `main`, and raises the project's
  version to it. That commit starts no further CI run. The entry's text is not the title: a language model writes it
  from the pull request's changes and description, as bullets under *Added*, *Changed*, *Fixed* and *Security* that say
  what a user, operator or integrator gets, with a breaking change marked as breaking and a link to the pull request.
  The text is written when the entry is first added and again whenever the author pushes changes, unless someone has
  edited it on the branch since CI last wrote it: an edited text is kept. When the title is edited or `main` moves on,
  CI renumbers the entry and the bump to the next free version and refreshes the date, keeping the text. When the model
  cannot be reached, the entry is the title's subject with the link, and the check says so. A `semver: none` pull
  request gets neither entry nor bump, and any entry or bump CI added earlier is removed.
- **The protocol only when it changes.** An entry names the metering-hook protocol
  ([PROT-27](../protocol/spec.md)) only in a release that changes it. A pull request that raises the protocol version
  MUST be marked breaking (`!`), or its entry check fails; its entry says the protocol changed, with a breaking bullet
  CI adds under *Changed* unless the text already names the protocol. A release whose protocol changed since the
  previous release tag and whose entry does not say so is refused before anything is published. The release notes
  always end with the protocol version, as DEP-11 requires.
- **The merge waits for CI.** `main` MUST only accept a pull request whose `ci-passed` check succeeded on its head.
  CI's own commits on the branch run no CI, so the result CI reached on the commit before them is set on the head as
  that check: pending until that run finishes, then its outcome.
- **Branches CI cannot write.** A pull request from a fork cannot receive the commit; its check fails and says so,
  and a maintainer brings the branch into the repository before merging.

#### Scenario: Feature title becomes a minor release
- **GIVEN** the version on `main` is `1.1.0`
- **WHEN** a pull request titled `feat(bundles): Order members by hand` is opened
- **THEN** it is labelled `type: feat` and `semver: minor`, and its branch gains a commit adding a `## [1.2.0] - <date>`
  entry whose bullets describe the pull request's changes and link to it, and raising the version to `1.2.0`

#### Scenario: Edited entry text is kept
- **GIVEN** a pull request whose entry text a maintainer reworded on the branch
- **WHEN** the author pushes another change
- **THEN** the entry keeps the reworded text, and only its version and date are updated

#### Scenario: Pushed changes rewrite an unedited entry
- **GIVEN** a pull request whose entry text is still the one CI wrote
- **WHEN** the author pushes a change that adds a new setting
- **THEN** the entry's text is written again from the changes and now mentions the setting

#### Scenario: Breaking change below 1.0 raises the minor
- **GIVEN** the version on `main` is `0.1.0`
- **WHEN** a pull request titled `refactor(auth)!: Rename the session cookie` is opened
- **THEN** it is labelled `semver: major`, and its entry and version are `0.2.0`, with the change marked as breaking

#### Scenario: Retitled pull request is re-derived
- **GIVEN** a pull request titled `fix(auth): Reject expired tokens` carrying a `1.1.1` entry
- **WHEN** its title is edited to `feat(auth): Accept refresh tokens`
- **THEN** its labels become `type: feat` and `semver: minor`, and its entry and version become `1.2.0`

#### Scenario: Main moving on renumbers the entry
- **GIVEN** two open pull requests that both carry a `1.2.0` entry
- **WHEN** one of them is merged
- **THEN** the other's entry and version are regenerated as `1.3.0` on its branch, above the merged `1.2.0` entry

#### Scenario: Documentation change is no release
- **WHEN** a pull request titled `docs(repo): Describe the release flow` is opened
- **THEN** it is labelled `type: docs` and `semver: none`, and its branch gains no entry and no version change

#### Scenario: Title that is no Conventional Commit fails
- **WHEN** a pull request titled `Update stuff` is opened
- **THEN** its title check fails naming the expected form, and no labels, entry or bump are added

#### Scenario: Unchanged protocol is not named
- **WHEN** a pull request that leaves the metering-hook protocol version as it is gets its entry
- **THEN** the entry does not mention the protocol

#### Scenario: Protocol change is named as breaking
- **GIVEN** the metering-hook protocol version on `main` is `2`
- **WHEN** a pull request titled `feat(metering)!: Tell the hook more` raises it to `3`
- **THEN** its entry carries a breaking bullet under *Changed* saying the protocol is now `3` and hooks must be updated

#### Scenario: Protocol change without a breaking title fails
- **WHEN** a pull request titled `feat(metering): Tell the hook more` raises the metering-hook protocol version
- **THEN** its entry check fails asking for `!` in the title, and no entry is committed

#### Scenario: Merge waits for CI on the commit before CI's
- **GIVEN** a pull request whose head is CI's entry commit, and CI still running on the author's commit before it
- **WHEN** someone tries to merge it
- **THEN** the merge is refused while the head's `ci-passed` is pending, and allowed once that run succeeds

#### Scenario: Description with a CI-skip marker fails
- **WHEN** a pull request's description quotes a commit subject ending in `[skip ci]`
- **THEN** its check fails asking to reword the description, before the merge could carry the marker to `main`

#### Scenario: The entry commit does not rerun CI
- **WHEN** CI commits the entry and the bump to a pull request's branch
- **THEN** no new CI run starts for that commit

#### Scenario: A long Dependabot title is shortened
- **WHEN** Dependabot opens a pull request titled
  `chore: Bump likec4 from 1.59.4 to 1.60.0 in /docs in the npm group across 1 directory`
- **THEN** CI retitles it `chore: Bump likec4 from 1.59.4 to 1.60.0 in /docs`, and the check passes with
  `type: chore` and `semver: none`
