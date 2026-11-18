# Spec Delta

## MODIFIED Requirements

### Requirement: ARC-2 Runtime versions
The gateway SHALL require Python ≥ 3.14 (`requires-python = ">=3.14"`, the first release with lazily evaluated
annotations, which the code relies on) and SHALL be built, tested and shipped on the latest stable Python release, 3.15
at the time of writing. The repository declares that version in one place, and every image that runs Python (the gateway
and the example upstreams) and every CI job that sets up Python uses exactly the declared version, except the backend
tests, which run on every version from the `requires-python` floor up to the declared one. The web app SHALL be built
and run on Node ≥ 24: `apps/web/package.json` declares it in `engines`, every CI and publishing job that runs Node uses
24 or later, and the web image runs Node 26.

#### Scenario: Gateway refuses an older Python
- **WHEN** the workspace is installed with a Python older than 3.14
- **THEN** `uv sync` rejects the interpreter because of `requires-python`

#### Scenario: Web app is built on Node 24 or later
- **WHEN** CI builds the web app or the web image is built
- **THEN** the Node version used is 24 or later

#### Scenario: Images and CI use the declared Python
- **GIVEN** the repository declares Python 3.15 as the shipped version
- **WHEN** an image's base or build stage, or a CI job, names a different Python version
- **THEN** the hermetic test suite fails and names the file and the version it found

#### Scenario: Shipped gateway runs the declared Python
- **WHEN** the gateway image is built and started
- **THEN** it runs on the declared Python version and reports ready

#### Scenario: Older Node is refused by the web app
- **WHEN** `npm ci` runs in `apps/web` under Node 22 with engine checks enforced
- **THEN** the install fails on the `engines` constraint

#### Scenario: No CI job runs an older Node
- **WHEN** the workflows under `.github/workflows/` are inspected
- **THEN** every `node-version` they set is 24 or later

#### Scenario: CI tests every supported Python
- **GIVEN** `requires-python = ">=3.14"` and Python 3.15 declared as the shipped version
- **WHEN** the backend test matrix in CI does not list exactly 3.14 and 3.15
- **THEN** the hermetic test suite fails and names the versions it expected and the ones CI tests
