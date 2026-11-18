## MODIFIED Requirements

### Requirement: DEP-10 CI gates
CI (GitHub Actions) MUST run on every pull request: `ruff` (including its security rules), `rumdl`, the import
contracts (`lint-imports`), `pytest`, the generated-OpenAPI drift check, the frontend typecheck (`npm run typecheck`)
and the frontend build, the docs build and documentation consistency checks, LikeC4 model validation
([DOC-10](../documentation/spec.md)), OpenSpec validation, the supply-chain security gate ([DEP-14](spec.md)), Docker
builds of both images, and the integration suite against the compose stack. Every job that installs the Python
workspace installs it from `uv.lock` as committed and fails when the lock no longer matches the project files, instead
of re-resolving it. A single `ci-passed` job fails unless every other job succeeded.

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

## ADDED Requirements

### Requirement: DEP-14 Supply-chain security gate
Every pull request and every push to `main` SHALL be checked for: known vulnerabilities in the locked Python and npm
dependencies, development dependencies included (npm at moderate severity or above); secrets in the commits it adds;
lint findings in any Dockerfile; and security findings of static analysis over the Python code. An advisory that
cannot be fixed yet passes only while it is listed, with a reason, in the repository's reviewed allow-list, whose
entries expire within 90 days.

#### Scenario: A locked dependency with a known vulnerability fails
- **GIVEN** a pull request whose `uv.lock` locks a Python package version with a published advisory
- **WHEN** CI runs
- **THEN** the security gate fails and names the package, its version and the advisory

#### Scenario: A moderate npm advisory fails
- **GIVEN** a pull request whose `apps/web` or `docs` lockfile locks a package with an advisory of moderate severity
  or above, in a production or a development dependency
- **WHEN** CI runs
- **THEN** the security gate fails and names the package and the advisory

#### Scenario: A low-severity npm advisory passes
- **GIVEN** the only advisory against an npm lockfile is of low severity
- **WHEN** CI runs
- **THEN** the security gate passes

#### Scenario: An allow-listed advisory passes
- **GIVEN** an advisory with no fixed release, listed in the allow-list with a reason and an expiry date
- **WHEN** CI runs before that date
- **THEN** the security gate passes and reports the advisory as accepted

#### Scenario: An expired allow-list entry fails
- **GIVEN** an allow-list entry whose expiry date has passed
- **WHEN** CI runs
- **THEN** the security gate fails and names the expired entry, whether or not its advisory is still reported

#### Scenario: An allow-list entry too far ahead is refused
- **WHEN** an allow-list entry's expiry is more than 90 days after the day CI runs
- **THEN** the security gate fails and names the entry

#### Scenario: A committed secret fails
- **GIVEN** a pull request with a commit that adds a private key or a live-looking access token
- **WHEN** CI runs
- **THEN** the security gate fails and names the file and the commit, without printing the secret

#### Scenario: A Dockerfile lint finding fails
- **GIVEN** a pull request that adds a Dockerfile instruction the linter reports, at any severity
- **WHEN** CI runs
- **THEN** the security gate fails and names the file, the line and the rule

#### Scenario: An insecure Python pattern fails
- **GIVEN** a pull request that adds library code calling a subprocess through a shell with interpolated input
- **WHEN** CI runs
- **THEN** CI fails on the static-analysis finding, naming the file, the line and the rule

### Requirement: DEP-15 Images are pinned by digest
Every image a Dockerfile builds from or copies from, and every image the compose files run, SHALL be referenced by a
version tag and its content digest, never by a moving tag alone, so a rebuild uses the bytes CI tested. Automated
update pull requests keep tags and digests current. The one exception is an image the compose file takes from an
operator-set variable for a service outside the default stack.

#### Scenario: An unpinned image fails the tests
- **GIVEN** a Dockerfile or compose file that names `node:26-alpine` or `example/image:latest` without a digest
- **WHEN** the hermetic test suite runs
- **THEN** it fails and names the file, the line and the image

#### Scenario: A moved tag does not change the build
- **GIVEN** a base image whose tag the publisher has since pointed at new contents
- **WHEN** the gateway image is rebuilt from an unchanged checkout
- **THEN** it is built from the same base image contents as before

#### Scenario: Pinned images still name their runtime version
- **GIVEN** the gateway's base image is referenced as `python:3.15.1-slim-bookworm@sha256:<digest>`
- **WHEN** the runtime-version check ([ARC-2](../architecture/spec.md)) runs
- **THEN** it reads Python `3.15` from that reference

#### Scenario: An operator-chosen fleet image may float
- **WHEN** a compose service outside the default stack takes its image from a variable such as `${FLEET_IMAGE:-…}`
- **THEN** its default may name a moving tag, and the test does not fail on it
