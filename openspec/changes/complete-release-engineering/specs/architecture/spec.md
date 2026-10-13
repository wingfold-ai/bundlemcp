## MODIFIED Requirements

### Requirement: ARC-2 Runtime versions
The gateway SHALL require Python ≥ 3.13 (`requires-python = ">=3.13"`) and SHALL be built, tested and shipped on the
latest stable Python release (3.14 at the time of writing: images on `python:3.14`, CI on 3.14). The web app SHALL be
built and run on Node ≥ 24: `apps/web/package.json` declares it in `engines`, every CI and publishing job that runs
Node uses 24 or later, and the web image runs Node 26.

#### Scenario: Gateway refuses an older Python
- **WHEN** the workspace is installed with a Python older than 3.13
- **THEN** `uv sync` rejects the interpreter because of `requires-python`

#### Scenario: Web app is built on Node 24 or later
- **WHEN** CI builds the web app or the web image is built
- **THEN** the Node version used is 24 or later

#### Scenario: Older Node is refused by the web app
- **WHEN** `npm ci` runs in `apps/web` under Node 22 with engine checks enforced
- **THEN** the install fails on the `engines` constraint

#### Scenario: No CI job runs an older Node
- **WHEN** the workflows under `.github/workflows/` are inspected
- **THEN** every `node-version` they set is 24 or later

#### Scenario: Gateway ships on the latest stable Python
- **WHEN** the gateway image is built
- **THEN** its interpreter is the latest stable Python release named in this requirement
