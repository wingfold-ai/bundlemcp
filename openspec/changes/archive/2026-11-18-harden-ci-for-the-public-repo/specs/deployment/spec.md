# Spec Delta

## ADDED Requirements

### Requirement: DEP-18 Code scanning
While the repository is public, CodeQL SHALL scan its Python, TypeScript and Vue code and its workflow files on every
pull request, on every push to `main` and weekly, using the extended security queries. Findings are listed under the
repository's code-scanning alerts. While the repository is private, the scan is skipped rather than failed.

#### Scenario: A pull request is scanned
- **GIVEN** the repository is public
- **WHEN** a pull request is opened
- **THEN** CodeQL analyses each of the three languages and reports new alerts on the pull request

#### Scenario: A private repository skips the scan
- **GIVEN** the repository is private
- **WHEN** CI runs
- **THEN** the CodeQL jobs are skipped, and no check fails because of them

### Requirement: DEP-19 Repository scorecard
While the repository is public, OpenSSF Scorecard SHALL rate it weekly, on every push to `main` and when its branch
rules change, publish the result for the badge the README shows, and list its findings under code scanning. While
the repository is private, the rating is skipped.

#### Scenario: The badge shows the current rating
- **GIVEN** the repository is public and Scorecard ran on `main`
- **WHEN** a visitor opens the README
- **THEN** the Scorecard badge shows that run's score and links to its report

## MODIFIED Requirements

### Requirement: DEP-10 CI gates
CI (GitHub Actions) MUST run on every pull request: `ruff` (including its security rules), `rumdl`, the import contracts
(`lint-imports`), `pytest`, the generated-OpenAPI drift check, the frontend typecheck (`npm run typecheck`) and the
frontend build, the docs build and documentation consistency checks, LikeC4 model validation
([DOC-10](../documentation/spec.md)), OpenSpec validation, the supply-chain security gate ([DEP-14](spec.md)), Docker
builds of both images, and the integration suite against the compose stack. The Python tests run on every Python version
the packages declare they support. CI SHALL also run every week on `main`, where the secret scan reads the whole
history, and every job SHALL have a time limit, so a job that hangs fails instead of running on. Every job that installs
the Python workspace installs it from `uv.lock` as committed and fails when the lock no longer matches the project
files, instead of re-resolving it. A single `ci-passed` job fails unless every other job succeeded.

#### Scenario: Any failing gate blocks the branch
- **WHEN** any CI job of a pull request fails
- **THEN** the `ci-passed` check fails

#### Scenario: A type error in the web app fails CI
- **GIVEN** a pull request that introduces a TypeScript type error in `apps/web` which `nuxt build` still bundles
- **WHEN** CI runs
- **THEN** the frontend job fails on the typecheck step, and `ci-passed` fails

#### Scenario: A stale lockfile fails CI
- **GIVEN** a pull request that adds a dependency to a `pyproject.toml` without updating `uv.lock`
- **WHEN** CI runs
- **THEN** the first job that installs the workspace fails, saying the lockfile needs to be updated, and `ci-passed`
  fails

#### Scenario: The security gate is required
- **WHEN** the supply-chain security gate of a pull request fails
- **THEN** the `ci-passed` check fails

#### Scenario: Every supported Python version is tested
- **GIVEN** the packages declare `requires-python = ">=3.14"`
- **WHEN** CI runs
- **THEN** the backend tests run on Python 3.14 and on 3.15, and either failing fails `ci-passed`

#### Scenario: A quiet week is still checked
- **GIVEN** no commit landed on `main` for a week
- **WHEN** the weekly run starts
- **THEN** CI runs on `main` as on a push, including the advisory gate and a secret scan of the whole history

#### Scenario: A hung job fails
- **WHEN** a CI job runs past its time limit
- **THEN** the job is cancelled as failed, and `ci-passed` fails

### Requirement: DEP-11 Image publishing
Images (`gateway`, `web`) MUST publish to ghcr.io on every push to `main`, tagged `:latest` (what a continuously
deployed stack pulls) and `:<commit-sha>` (to pin or roll back to an exact build). Releases SHALL publish on tags: a
`v<major>.<minor>.<patch>` tag publishes both images as `:<major>.<minor>.<patch>` and creates a release whose notes
come from the changelog's entry for that version. A merge into `main` that raises the version
([DEP-12](spec.md)) creates that version's tag and publishes its release without anyone pushing a tag; a tag a
maintainer pushes by hand publishes the same way. Every release's notes SHALL state the metering-hook protocol version
([PROT-27](../protocol/spec.md)) and call it out when it changed since the previous release. Every published image SHALL
carry an SBOM and a SLSA provenance record; in a public repository it SHALL also carry a provenance attestation signed
by GitHub that names the workflow and the commit it was built from.

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

#### Scenario: A published image can be verified
- **GIVEN** the repository is public and an image was published by the publish workflow
- **WHEN** an operator runs `gh attestation verify oci://ghcr.io/<owner>/bundlemcp-gateway:<tag> --owner <owner>`
- **THEN** the verification succeeds and names this repository's workflow and the commit the image was built from

#### Scenario: A published image lists its contents
- **WHEN** an operator inspects a published image's attestations in the registry
- **THEN** it carries an SBOM of the packages in the image and a provenance record of its build
