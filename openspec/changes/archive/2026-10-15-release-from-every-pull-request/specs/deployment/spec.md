## MODIFIED Requirements

### Requirement: DEP-11 Image publishing
Images (`gateway`, `web`) MUST publish to ghcr.io on every push to `main`, tagged `:latest` (what a continuously
deployed stack pulls) and `:<commit-sha>` (to pin or roll back to an exact build). Releases SHALL publish on tags: a
`v<major>.<minor>.<patch>` tag publishes both images as `:<major>.<minor>.<patch>` and creates a release whose notes
come from the changelog's entry for that version. A merge into `main` that raises the version
([DEP-12](spec.md)) creates that version's tag and publishes its release without anyone pushing a tag; a tag a
maintainer pushes by hand publishes the same way. Every release's notes SHALL state the metering-hook protocol version
([PROT-27](../protocol/spec.md)) and call it out when it changed since the previous release.

#### Scenario: Push to main publishes both images
- **WHEN** a commit lands on `main`
- **THEN** `bundlemcp-gateway` and `bundlemcp-web` are pushed to ghcr.io as `:latest` and `:<that commit's sha>`

#### Scenario: Merge that raises the version releases it
- **GIVEN** the version on `main` is `1.1.0`
- **WHEN** a pull request that raises it to `1.2.0` is merged
- **THEN** the merge commit is tagged `v1.2.0`, both images are pushed as `:1.2.0`, and a release `v1.2.0` is created
  with the changelog's `1.2.0` entry as its notes

#### Scenario: Merge that keeps the version releases nothing
- **WHEN** a pull request that does not change the version is merged
- **THEN** no tag and no release is created

#### Scenario: Release tag publishes a versioned release
- **WHEN** the tag `v1.2.0` is pushed
- **THEN** both images are pushed as `:1.2.0`, and a release `v1.2.0` is created with the changelog's `1.2.0` entry as
  its notes

#### Scenario: Metering protocol change is called out
- **GIVEN** the metering-hook protocol version differs from the one the previous release shipped
- **WHEN** the release is created
- **THEN** its notes name the new protocol version and say that it changed

#### Scenario: Tag without a changelog entry is refused
- **WHEN** a release tag is pushed for a version the changelog has no entry for
- **THEN** the release workflow fails before publishing anything

## ADDED Requirements

### Requirement: DEP-12 Every pull request carries its release
A pull request into `main` SHALL carry the release its merge makes, so the squash commit is the release commit and
`main` gains no other commit for it.

- **Labels from the title.** The pull request's title MUST be a Conventional Commit (`<type>(<scope>)!: <Subject>`).
  CI derives a `type: <type>` label and a `semver:` label from it, and replaces both whenever the title is edited: `!`
  is `semver: major`; otherwise `feat` is `minor`, `fix`, `perf` and `revert` are `patch`, and every other type is
  `none`. A title that is not a Conventional Commit fails the check and gets no labels.
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

#### Scenario: The entry commit does not rerun CI
- **WHEN** CI commits the entry and the bump to a pull request's branch
- **THEN** no new CI run starts for that commit
